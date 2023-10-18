from dataclasses import dataclass
from typing import Union, List, Set, Optional, Type, TypeAlias, Dict
from abc import ABC, abstractmethod

Id = bytes
View = int
Committee = Set[Id]


def int_to_id(i: int) -> Id:
    return bytes(str(i), encoding="utf8")


@dataclass(unsafe_hash=True)
class StandardQc:
    block: Id
    view_num: View  # Changed the variable name to avoid conflict with the class name
    Comm_No: int  # This committee position in the set of committees

    # If it is false then the QC is built by the committees with 2/3 collection of votes from subtree of the collector
    # committee.

    def view(self) -> View:
        return self.view_num  # Changed the method name to view_num


@dataclass
class AggregateQc:
    qcs: List[View]
    highest_qc: StandardQc
    view_num: View  # Changed the variable name to avoid conflict with the class name

    def view(self) -> View:
        return self.view_num  # Changed the method name to view_num

    def high_qc(self) -> StandardQc:
        assert self.highest_qc.view() == max(self.qcs)  # Corrected method call
        assert self.highest_qc.root_qc, "Expected self.highest_qc.root_qc to be True"
        return self.highest_qc


Qc = Union[StandardQc, AggregateQc]  # Changed the type alias to use Union


@dataclass
class Block:
    view_num: View  # Changed the variable name to avoid conflict with the class name
    qc: Qc
    _id: Id

    def extends(self, ancestor):
        if self == ancestor:
            return True
        elif self.parent is None:
            return False
        elif self.parent.view < ancestor.view:  # Check the view of the parent
            return False
        else:
            return self.parent.extends(ancestor)

    def parent(self) -> Id:
        if isinstance(self.qc, StandardQc):
            return self.qc.block
        elif isinstance(self.qc, AggregateQc):
            return self.qc.high_qc().block

    def id(self) -> Id:
        return self._id


@dataclass(unsafe_hash=True)
class Vote:
    block: Id
    view: View
    voter: Id
    qc: Optional[Qc]


@dataclass
class TimeoutQc:
    view: View
    high_qc: Qc
    qc_views: List[View]
    sender_ids: Set[Id]
    sender: Id


class Timeout:
    view: View
    high_qc: Qc
    sender: Id
    timeout_qc: Type[TimeoutQc]


@dataclass
class NewView:
    view: View
    high_qc: Qc
    sender: Id
    timeout_qc: Type[TimeoutQc]


Quorum: TypeAlias = Union[Set[Vote], Set[NewView]]

Payload: TypeAlias = Union[Block, Vote, Timeout, NewView, TimeoutQc]


@dataclass
class BroadCast:
    payload: Payload


@dataclass
class Send:
    to: [Id]
    payload: Payload


Event: TypeAlias = Union[BroadCast, Send]


class Overlay:
    """
    Overlay structure for a View
    """

    @abstractmethod
    def is_leader(self, _id: Id):
        """
        :param _id:  Node id to be checked
        :return: true if node is the leader of the current view
        """
        return _id == self.leader()

    @abstractmethod
    def leader(self) -> Id:
        """
        :param view:
        :return: the leader Id of the specified view
        """
        pass

    @abstractmethod
    def next_leader(self) -> Id:
        pass

    @abstractmethod
    def is_member_of_leaf_committee(self, _id: Id) -> bool:
        """
        :param _id: Node id to be checked
        :return: true if the participant with Id _id is in the leaf committee of the committee overlay
        """
        pass

    @abstractmethod
    def is_member_of_root_committee(self, _id: Id) -> bool:
        """
        :param _id:
        :return: true if the participant with Id _id is member of the root committee withing the tree overlay
        """
        pass

    @abstractmethod
    def is_member_of_my_committee(self, _id: Id) -> bool:
        """
        :param _id:
        :return: true if the participant with Id _id is member of the committee of the  verifying node withing the tree overlay
        """
        pass

    @abstractmethod
    def is_member_of_child_committee(self, parent: Id, child: Id) -> bool:
        """
        :param parent:
        :param child:
        :return: true if participant with Id child is member of the child committee of the participant with Id parent
        """
        pass

    def is_member_of_subtree(self, root_node: Id, child: Id) -> bool:
        """
        :param root_node:
        :param child:
        :return: true if participant with Id  is member of a committee in the subtree of the participant with Id root_node
        """
        pass
    @abstractmethod
    def parent_committee(self, _id: Id) -> Optional[Committee]:
        """
        :param _id:
        :return: Some(parent committee) of the participant with Id _id withing the committee tree overlay
        or Empty if the member with Id _id is a participant of the root committee
        """
        pass

    @abstractmethod
    def leaf_committees(self) -> Set[Committee]:
        pass

    @abstractmethod
    def root_committee(self) -> Committee:
        """
        :return: returns root committee
        """
        pass

    @abstractmethod
    def my_committee(self, _id: Id) -> Optional[Committee]:
        """
        :param _id:
        :return: Some(committee) of the participant with Id _id withing the committee tree overlay
        """
        pass

    @abstractmethod
    def is_child_of_root_committee(self, _id: Id) -> bool:
        """
        :return: returns child committee/s of root committee if present
        """
        pass

    @abstractmethod
    def leader_super_majority_threshold(self, _id: Id) -> int:
        """
        Amount of distinct number of messages for a node with Id _id member of a committee
        The return value may change depending on which committee the node is member of, including the leader
        :return:
        """
        pass

    @abstractmethod
    def super_majority_threshold(self, _id: Id) -> int:
        pass


class Carnot:
    def __init__(self, _id: Id, overlay=Overlay()):
        self.id: Id = _id
        self.current_view: View = 0
        self.highest_voted_view: View = -1
        self.local_high_qc: Type[Qc] = None
        self.safe_blocks: Dict[Id, Block] = dict()
        self.last_view_timeout_qc: Type[TimeoutQc] = None
        self.overlay: Overlay = overlay

    def can_commit_grandparent(self, block) -> bool:
        # Get the parent block and grandparent block from the safe_blocks dictionary
        parent = self.safe_blocks.get(block.parent())
        grandparent = self.safe_blocks.get(parent.parent())

        # Check if both parent and grandparent exist
        if parent is None or grandparent is None:
            return False

        # Check if the view numbers and QC types match the expected criteria
        is_view_incremented = parent.view == grandparent.view + 1
        is_standard_qc = isinstance(block.qc, StandardQc) and isinstance(parent.qc, StandardQc)

        # Return True if both conditions are met
        return is_view_incremented and is_standard_qc

    def latest_committed_view(self) -> View:
        return self.latest_committed_block().view

    # Return a list of blocks received by a node for a specific view.
    # More than one block is returned only in case of a malicious leader.
    def blocks_in_view(self, view: View) -> List[Block]:
        return [block for block in self.safe_blocks.values() if block.view == view]

    def genesis_block(self) -> Block:
        return self.blocks_in_view(0)[0]

    def latest_committed_block(self) -> Block:
        for view in range(self.current_view, 0, -1):
            for block in self.blocks_in_view(view):
                if self.can_commit_grandparent(block):
                    return self.safe_blocks.get(self.safe_blocks.get(block.parent()).parent())
        # The genesis block is always considered committed.
        return self.genesis_block()

    def block_is_safe(self, block: Block) -> bool:
        if isinstance(block.qc, StandardQc):
            return block.view_num == block.qc.view() + 1
        elif isinstance(block.qc, AggregateQc):
            return block.view_num == block.qc.view() + 1 and block.extends(self.latest_committed_block())
        else:
            return False

    def update_high_qc(self, qc: Qc):
        match (self.local_high_qc, qc):
            case (None, new_qc) if isinstance(new_qc, StandardQc):
                # Set local high QC to the new StandardQc
                self.local_high_qc = new_qc
            case (None, new_qc) if isinstance(new_qc, AggregateQc):
                # Set local high QC to the high QC from the new AggregateQc
                self.local_high_qc = new_qc.high_qc()
            case (old_qc, new_qc) if isinstance(new_qc, StandardQc) and new_qc.view > old_qc.view:
                # Update local high QC if the new StandardQc has a higher view
                self.local_high_qc = new_qc
            case (old_qc, new_qc) if isinstance(new_qc,
                                                AggregateQc) and new_qc.high_qc().view != old_qc.view and new_qc.view > old_qc.view:
                # Update local high QC if the view of the high QC in the new AggregateQc is different
                self.local_high_qc = new_qc.high_qc()

        # If my view is not updated, I update it when I see a QC for that view
        if qc.view >= self.current_view:
            self.current_view = qc.view + 1

    def update_timeout_qc(self, timeout_qc: TimeoutQc):
        if not self.last_view_timeout_qc or timeout_qc.view > self.last_view_timeout_qc.view:
            self.last_view_timeout_qc = timeout_qc

    def receive_block(self, block: Block):
        assert block.parent() in self.safe_blocks

        # Check if the block is already in safe_blocks, if it's from a previous view,
        # or if there are existing blocks for the same view
        if block.id() in self.safe_blocks or block.view <= self.latest_committed_view() or self.blocks_in_view(
                block.view):
            # TODO: Report malicious leader or handle potential fork divergence
            return

        # TODO: Verify if the proposer is indeed the leader

        # If the block is safe, add it to safe_blocks and update the high QC
        if self.block_is_safe(block):
            self.safe_blocks[block.id()] = block
            self.update_high_qc(block.qc)

    def approve_block(self, block: Block, votes: Set[Vote]) -> Event:
        # Assertions for input validation
        assert block.id() in self.safe_blocks
        # This assertion will be moved outside as the approve_block will be called in two cases:
        # 1st the fast path when len(votes) == self.overlay.super_majority_threshold(self.id) and the second
        # When there is the first timeout t1 for the fast path and the protocol operates in the slower path
        # in this case the node will prepare a QC from votes it has received.
        # assert len(votes) == self.overlay.super_majority_threshold(self.id)
        assert all(self.overlay.is_member_of_my_committee(self.id, vote.voter) for vote in votes)
        assert all(vote.block == block.id() for vote in votes)
        assert self.highest_voted_view < block.view

        # Create a QC based on committee membership
        qc = self.build_qc(block.view, block, None)  # if self.overlay.is_member_of_root_committee(self.id) else None

        # Create a new vote
        vote = Vote(
            block=block.id(),
            voter=self.id,
            view=block.view,
            qc=qc
        )

        # Update the highest voted view
        self.highest_voted_view = max(self.highest_voted_view, block.view)

        # Determine the recipient based on committee membership
        if self.overlay.is_member_of_root_committee(self.id):
            recipient = self.overlay.leader(block.view + 1)
        else:
            recipient = self.overlay.parent_committee(self.id)

        # Return a Send event to the appropriate recipient
        return Send(to=recipient, payload=vote)

    from typing import Optional, Set, List


# A committee member builds a QC or timeout QC with at least two-thirds of votes from its sub-branch within the overlay.
    #Furthermore, if a node builds a timeout QC with at least f+1 timeout messages, it forwards them to its parents
    # as well as the child committee. This allows any node that have not timed out to timeout.
    def build_qc(self, view: int, block: Optional[Block] = None, Timeouts: Optional[Set[Timeout]] = None,
                 votes: Optional[List[Vote]] = None) -> Qc:
        if Timeout:
            # Unhappy path: Aggregate QC
            new_timeout_list = list(Timeouts)
            highest_qc = max(new_timeout_list, key=lambda x: x.high_qc.view).high_qc
            return AggregateQc(
                qcs=[msg.high_qc.view for msg in new_timeout_list],
                highest_qc=highest_qc,
                view=new_timeout_list[0].view
            )
        else:
            # Happy path: Standard QC
            if votes:
                # Use vote.block if votes are available
                block_id = votes[0].block
            elif block:
                # Use the provided block if votes are not available
                block_id = block.id()
            else:
                # No block or votes provided, return None
                return None

            return StandardQc(
                view=view,
                block=block_id
            )

   # A node initially forwards a QC
    def forward_vote(self, vote: Optional[Vote] = None, qc: Optional[Qc] = None) -> Optional[Event]:
        # Assertions for input validation if vote is provided
        if vote:
            assert vote.block in self.safe_blocks
            assert self.overlay.is_member_of_subtree(self.id, vote.voter), "Voter should be a member of the subtree"
            assert self.highest_voted_view == vote.view, "Can only forward votes after voting ourselves"

        # Assertions for input validation if QC is provided
        if qc:
            assert qc.view >= self.current_view, "QC view should be greater than or equal to the current view"
            assert qc.view >= self.highest_voted_view, "QC view should be greater than or equal to the highest voted view"
            assert all(
                self.overlay.is_member_of_subtree(self.id, voter)
                for voter in qc.voters
            ), "All voters in QC should be members of the subtree"

        if self.overlay.is_member_of_root_committee(self.id):
            # Forward the vote or QC to the next leader in the root committee
            recipient = self.overlay.next_leader()
        else:
            # Forward the vote or QC to the parent committee
            recipient = self.overlay.parent_committee

        # Create a Send event with either vote or QC as payload and return it
        if vote:
            return Send(to=recipient, payload=vote)
        elif qc:
            return Send(to=recipient, payload=qc)
        else:
            # If neither vote nor QC is provided, return None
            return None


    def forward_timeout_qc(self, msg: TimeoutQc) -> Optional[Event]:
        # Assertions for input validation
        assert msg.view == self.current_view, "Received TimeoutQc with correct view"
        assert self.overlay.is_member_of_child_committee(self.id, msg.sender)
               #or self.overlay.is_member_of_my_committee(self.id, msg.sender), "Sender is  a member of child committee"
        assert self.highest_voted_view == msg.view, "Can only forward NewView after voting ourselves"

        if self.overlay.is_member_of_root_committee(self.id):
            # Forward the NewView message to the next leader in the root committee
            return Send(to=self.overlay.next_leader(), payload=msg)
        else:
            # Forward the NewView message to the parent committee
            return Send(to=self.overlay.parent_committee, payload=msg)

    def propose_block(self, view: View, quorum: Quorum) -> Event:
        # Check if the node is a leader and if the quorum size is sufficient
        assert self.overlay.is_leader(self.id), "Only leaders can propose blocks"
        assert len(quorum) >= self.overlay.leader_super_majority_threshold(self.id), "Sufficient quorum size is allowed"

        # Initialize QC to None
        qc = None

        # Extract the first element from the quorum
        first_quorum_item = quorum[0]

        if isinstance(first_quorum_item, Vote):
            # Happy path: Create a QC based on votes in the quorum
            vote = first_quorum_item
            assert vote.block in self.safe_blocks
            qc = self.build_qc(vote.view, self.safe_blocks[vote.block], None)
        elif isinstance(first_quorum_item, NewView):
            # Unhappy path: Create a QC based on NewView messages in the quorum
            new_view = first_quorum_item
            qc = self.build_qc(new_view.view, None, quorum)

        # Generate a new Block with a dummy ID for proposing the next block
        block = Block(
            view=view,
            qc=qc,
            # Dummy ID for proposing the next block
            _id=int_to_id(hash((f"View-{view}", f"QC-View-{qc.view}")))
        )

        # Return a Broadcast event with the proposed block
        return BroadCast(payload=block)

    def local_timeout(self) -> Optional[Event]:
        """
        Root committee changes for each failure, so repeated failure will be handled by different
        root committees
        """
        # avoid voting after we timeout
        self.highest_voted_view = self.current_view

        timeout_msg: Timeout = Timeout(
            view=self.current_view,
            high_qc=self.local_high_qc,
            # local_timeout is only true for the root committee or members of its children
            # root committee or its children can trigger the timeout.
            timeout_qc=self.last_view_timeout_qc,
            sender=self.id
        )
        return Send(payload=timeout_msg, to=self.overlay.my_committee())


def receive_timeout_qc(self, timeout_qc: TimeoutQc):
    if timeout_qc.view < self.current_view:
        # Ignore outdated timeout QC
        return

    # Update the local high QC with the new high QC from the timeout QC
    self.update_high_qc(timeout_qc.high_qc)

    # Update the last view timeout QC
    self.update_timeout_qc(timeout_qc)

    # Update the current view based on the timeout QC
    self.update_current_view_from_timeout_qc(timeout_qc)

    # Optionally, rebuild the overlay from the timeout QC
    # self.rebuild_overlay_from_timeout_qc(timeout_qc)

# The overlay can be built using a random seed for any random source.
# Here we assume the TimeoutQC is the seed.
def rebuild_overlay_from_timeout_qc(self, timeout_qc: TimeoutQc):
    # Ensure the timeout QC view is greater than or equal to the current view
    assert timeout_qc.view >= self.current_view, "Timeout QC view should be greater than or equal to current view"

    # Rebuild the overlay from scratch
    self.overlay = Overlay()


@staticmethod
def build_timeout_qc(msgs: Set[Timeout], sender: Id) -> TimeoutQc:
    # Convert the set of Timeout messages to a list
    msgs_list = list(msgs)

    # Extract the view and high QC from the list of messages
    view = msgs_list[0].view
    high_qc_list = [msg.high_qc for msg in msgs_list]

    # Find the highest high QC using the max function
    high_qc = max(high_qc_list, key=lambda x: x.view)

    # Extract the QC views and sender IDs
    qc_views = [msg.view for msg in msgs_list]
    sender_ids = {msg.sender for msg in msgs_list}

    # Build the TimeoutQc object
    return TimeoutQc(
        view=view,
        high_qc=high_qc,
        qc_views=qc_views,
        sender_ids=sender_ids,
        sender=sender
    )


def update_current_view_from_timeout_qc(self, timeout_qc: TimeoutQc):
    self.current_view = timeout_qc.view + 1 if timeout_qc.view >= self.current_view else self.current_view

def is_safe_to_timeout_invariant(self):
    # Ensure that the current view is always higher than the highest voted view or the local high QC view.
    assert self.current_view > max(self.highest_voted_view - 1, self.local_high_qc.view), "Current view should be higher than the highest voted view or local high QC view."

    # Ensure that a node waits for the timeout QC from the root committee or the last view timeout QC
    # from the previous view before changing its view.
    assert (
        self.current_view == self.local_high_qc.view + 1 or
        self.current_view == self.last_view_timeout_qc.view + 1 or
        self.current_view == self.last_view_timeout_qc.view
    ), "Node must wait for appropriate QC before changing its view."

    # If both assertions pass, the invariant is satisfied
    return True
