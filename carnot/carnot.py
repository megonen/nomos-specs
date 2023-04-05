from dataclasses import dataclass
from typing import TypeAlias, List, Set, Self, Optional, Dict, FrozenSet
from abc import abstractmethod

Id: TypeAlias = bytes
View: TypeAlias = int
Committee: TypeAlias = Set[Id]


def int_to_id(i: int) -> Id:
    return bytes(str(i), encoding="utf8")


@dataclass(unsafe_hash=True)
class StandardQc:
    block: Id
    view: View

    def view(self) -> View:
        return self.view


@dataclass
class AggregateQc:
    qcs: List[View]
    highest_qc: StandardQc
    view: View

    def view(self) -> View:
        return self.view

    def high_qc(self) -> StandardQc:
        assert self.highest_qc.view == max(self.qcs)
        return self.highest_qc


Qc: TypeAlias = StandardQc | AggregateQc


@dataclass
class Block:
    view: View
    qc: Qc
    content: FrozenSet[Id]

    def extends(self, ancestor: Self) -> bool:
        """
        :param ancestor:
        :return: true if block is descendant of the ancestor in the chain
        """
        return self.view > ancestor.view

    def parent(self) -> Id:
        return self.qc.block

    def id(self) -> Id:
        return int_to_id(hash(self.content))


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


# local timeout field is only used by the root committee and its children when they timeout. The timeout_qc is built
# from local_timeouts. Leaf nodes when receive timeout_qc build their timeout msg and includes the timeout_qc in it.
# The timeout_qc is indicator that the root committee and its child committees (if exist) have failed to collect votes.
@dataclass
class Timeout:
    view: View
    high_qc: Qc
    sender: Id
    timeout_qc: TimeoutQc
    local_timeout: bool


Quorum: TypeAlias = Set[Vote] | Set[Timeout]


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
        pass

    def is_child_of_root(self, _id: Id):
        """
         :param _id:  Node id to be checked
         :return: true if node is the member of child of the root committee
         """
        pass

    def number_of_committees(self, _ids: set[Id]) -> int:
        """
        :param _ids:  Set of Node id to be checked
        :return: Number of committees in the overlay
        """
        pass

    def leader(self, view: View) -> Id:
        """
        :param view:
        :return: the leader Id of the specified view
        """
        pass

    @abstractmethod
    def member_of_leaf_committee(self, _id: Id) -> bool:
        """
        :param _id: Node id to be checked
        :return: true if the participant with Id _id is in the leaf committee of the committee overlay
        """
        pass

    @abstractmethod
    def member_of_root_committee(self, _id: Id) -> bool:
        """
        :param _id:
        :return: true if the participant with Id _id is member of the root committee withing the tree overlay
        """
        pass

    @abstractmethod
    def member_of_root_com(self, _id: Id) -> bool:
        """
        :param _id:
        :return: true if the participant with Id _id is member of the root committee withing the tree overlay
        """
        pass

    @abstractmethod
    def member_of_internal_com(self, _id: Id) -> bool:
        """
        :param _id:
        :return:  True if the participant with Id _id is member of internal committees within the committee tree overlay
        """
        pass

    @abstractmethod
    def child_committee(self, parent: Id, child: Id) -> bool:
        """
        :param parent:
        :param child:
        :return: true if participant with Id child is member of the child committee of the participant with Id parent
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

    def leaf_committees(self) -> Set[Committee]:
        pass

    def root_committee(self) -> Committee:
        """
        :return: returns root committee
        """
        pass

    def child_of_root_committee(self, _id: Id) -> Optional[Set[Committee]]:
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
    def root_super_majority_threshold(self, _id: Id) -> int:
        pass

    @abstractmethod
    def super_majority_threshold(self, _id: Id) -> int:
        pass


def download(view) -> Block:
    raise NotImplementedError


def is_sequential_ascending(view1: View, view2: View):
    return view1 == view2 + 1


class Carnot:
    def __init__(self, _id: Id):
        self.id: Id = _id
        # Current View counter
        self.current_view: View = 0
        # Highest voted view counter. This is used to prevent a node from voting twice or vote after timeout.
        self.highest_voted_view: View = 0
        # This is the qc from  the highest view a node has
        self.local_high_qc: Optional[Qc] = None
        # The latest view committed by a node.
        self.latest_committed_view: View = 0
        #
        self.safe_blocks: Dict[Id, Block] = dict()
        self.seen_view_blocks: Dict[View, bool] = dict()
        self.last_timeout_view_qc: Optional[TimeoutQc] = None
        self.last_timeout_view: Optional[View] = None
        self.overlay: Overlay = Overlay()  # TODO: integrate overlay
        self.committed_blocks: Dict[Id, Block] = dict()

    def block_is_safe(self, block: Block) -> bool:
        match block.qc:
            case StandardQc() as standard:
                if standard.view < self.latest_committed_view:
                    return False
                return block.view >= self.latest_committed_view and \
                    self.is_sequential_ascending(block.view, standard.view)
            case AggregateQc() as aggregated:
                if aggregated.high_qc().view < self.latest_committed_view:
                    return False
                return block.view >= self.current_view and \
                    self.is_sequential_ascending(block.view, aggregated.view)

    # Ask Dani
    def update_high_qc(self, qc: Qc):
        match (self.local_high_qc, qc):
            case (None, StandardQc() as new_qc):
                self.local_high_qc = new_qc
            case (None, AggregateQc() as new_qc):
                self.local_high_qc = new_qc.high_qc()
            case (old_qc, StandardQc() as new_qc) if new_qc.view > old_qc.view:
                self.local_high_qc = new_qc
            case (old_qc, AggregateQc() as new_qc) if new_qc.high_qc().view != old_qc.view:
                self.local_high_qc = new_qc.high_qc()

    def update_timeout_qc(self, timeout_qc: TimeoutQc):
        match (self.last_timeout_view_qc, timeout_qc):
            case (None, timeout_qc):
                self.local_high_qc = timeout_qc
            case (self.last_timeout_view_qc, timeout_qc) if timeout_qc.view > self.last_timeout_view_qc.view:
                self.last_timeout_view_qc = timeout_qc

    def receive_block(self, block: Block):
        assert block.parent() in self.safe_blocks

        if block.id() in self.safe_blocks:
            return
        if self.seen_view_blocks.get(block.view) is not None or block.view <= self.latest_committed_view:
            # TODO: Report malicious leader
            return

        if self.block_is_safe(block):
            self.safe_blocks[block.id()] = block
            self.seen_view_blocks[block.view] = True
            self.update_high_qc(block.qc)
            self.try_commit_grand_parent(block)

    def vote(self, block: Block, votes: Set[Vote]):
        assert block.id() in self.safe_blocks
        assert len(votes) == self.overlay.super_majority_threshold(self.id)
        assert all(self.overlay.child_committee(self.id, vote.voter) for vote in votes)
        assert all(vote.block == block.id() for vote in votes)
        assert block.view > self.highest_voted_view

        if self.overlay.member_of_root_com(self.id):
            vote: Vote = Vote(
                block=block.id(),
                voter=self.id,
                view=self.current_view,
                qc=self.build_qc(votes)
            )
            self.send(vote, self.overlay.leader(self.current_view + 1))
        else:
            vote: Vote = Vote(
                block=block.id(),
                voter=self.id,
                view=self.current_view,
                qc=None
            )
            self.send(vote, *self.overlay.parent_committee(self.id))
        self.increment_voted_view(block.view)  # to avoid voting again for this view.
        self.increment_view_qc(block.qc)

    def forward_vote(self, vote: Vote):
        assert vote.block in self.safe_blocks
        assert self.overlay.child_committee(self.id, vote.voter)

        if self.overlay.member_of_root_com(self.id):
            self.send(vote, self.overlay.leader(self.current_view + 1))

    def build_qc(self, quorum: Quorum) -> Qc:
        pass

    def propose_block(self, view: View, quorum: Quorum):
        assert self.overlay.is_leader(self.id)
        assert len(quorum) == self.overlay.leader_super_majority_threshold(self.id)

        qc = self.build_qc(quorum)
        block = Block(view=view, qc=qc)
        self.broadcast(block)

    def local_timeout(self, new_overlay: Overlay):
        # This condition makes sure a node waits for timeout_qc from root committee to change it's view.
        assert (is_sequential_ascending(self.current_view, self.local_high_qc.view) or
                is_sequential_ascending(self.current_view, self.last_timeout_view_qc.view))
        self.increment_voted_view(self.current_view)

        if self.overlay.member_of_root_committee(self.id) or self.overlay.child_of_root_committee(self.id):
            timeout_msg: Timeout = Timeout(
                view=self.current_view,
                high_qc=self.local_high_qc,
                local_timeout=True,
                # local_timeout is only true for the root committee or members of its children
                # root committee or its children can trigger the timeout.
                timeout_qc=self.last_timeout_view_qc,
                sender=self.id
            )
            self.send(timeout_msg, *self.overlay.root_committee())

    def timeout(self, msgs: Set[Timeout]):
        assert len(msgs) == self.overlay.super_majority_threshold(self.id)
        assert all(msg.view >= self.current_view for msg in msgs)
        assert len(set(msg.view for msg in msgs)) == 1

        max_msg = self.get_max_timeout(msgs)
        if self.local_high_qc.view < max_msg.high_qc.view:
            self.update_high_qc(max_msg.high_qc)

        if self.overlay.member_of_root_committee(self.id) or self.overlay.child_of_root_committee(self.id):
            timeout_qc = self.build_timeout_qc(msgs)
            self.update_timeout_qc(timeout_qc)
        else:
            self.update_timeout_qc(msgs.pop().timeout_qc)

    def detected_timeout(self, msgs: Set[Timeout]):
        assert len(msgs) == self.overlay.leader_super_majority_threshold(self.id)
        assert all(msg.view >= self.current_view for msg in msgs)
        assert len(set(msg.view for msg in msgs)) == 1
        assert all(msg.local_timeout for msg in msgs)
        assert self.overlay.member_of_root_committee(self.id) or self.overlay.child_of_root_committee(self.id)

        timeout_qc = self.build_timeout_qc(msgs)
        self.update_timeout_qc(timeout_qc)
        self.update_high_qc(timeout_qc.high_qc)
        self.rebuild_overlay_from_timeout_qc(timeout_qc)
        self.send(timeout_qc, *self.overlay.leaf_committees())  # should be sent only to the leafs

    def gather_timeouts(self, timeouts: Set[Timeout]):
        assert not self.overlay.member_of_leaf_committee(self.id)
        assert len(set(timeout.view for timeout in timeouts)) == 1
        assert all(timeout.view >= self.current_view for timeout in timeouts)
        assert all(timeout.view == timeout.timeout_qc.view for timeout in timeouts)
        assert len(timeouts) == self.overlay.super_majority_threshold(self.id)
        assert all(self.overlay.child_committee(self.id, timeout.sender) for timeout in timeouts)

        timeouts = list(timeouts)
        timeout_qc = timeouts[0].timeout_qc
        new_high_qc = timeout_qc.high_qc

        self.rebuild_overlay_from_timeout_qc(timeout_qc)

        if new_high_qc.view >= self.local_high_qc.view:
            self.update_high_qc(new_high_qc)
            self.update_timeout_qc(timeout_qc)
            self.increment_view_timeout_qc(timeout_qc)

        if self.overlay.member_of_root_com(self.id):
            timeout_msg = Timeout(
                view=self.current_view,
                high_qc=self.local_high_qc,
                sender=self.id,
                timeout_qc=timeout_qc,
                local_timeout=False,
            )
            self.send(timeout_msg, self.overlay.leader(self.current_view + 1))
        else:
            timeout_msg = Timeout(
                view=self.current_view,
                high_qc=self.local_high_qc,
                sender=self.id,
                timeout_qc=timeout_qc,
                local_timeout=False,
            )
            self.send(timeout_msg, *self.overlay.parent_committee(self.id))
        self.increment_view_timeout_qc(timeout_qc)
        # This checks if a not has already incremented its voted view by local_timeout. If not then it should
        # do it now to avoid voting in this view.
        if self.highest_voted_view < self.current_view:
            self.increment_voted_view(timeout_qc.view)

    def received_timeout_qc(self, timeout_qc: TimeoutQc):
        assert timeout_qc.view >= self.current_view
        self.rebuild_overlay_from_timeout_qc(timeout_qc)

        if self.overlay.member_of_leaf_committee(self.id):
            new_high_qc = timeout_qc.high_qc
            if new_high_qc.view >= self.local_high_qc.view:
                self.update_high_qc(new_high_qc)
                self.update_timeout_qc(timeout_qc)
                self.increment_view_timeout_qc(timeout_qc)
            timeout_msg = Timeout(
                view=self.current_view,
                high_qc=self.local_high_qc,
                sender=self.id,
                timeout_qc=timeout_qc,
                local_timeout=False,
            )
            self.send(timeout_msg, *self.overlay.parent_committee(self.id))
            # This checks if a not has already incremented its voted view by local_timeout. If not then it should
            # do it now to avoid voting in this view.
            if self.highest_voted_view < self.current_view:
                self.increment_voted_view(timeout_qc.view)

    def rebuild_overlay_from_timeout_qc(self, timeout_qc: TimeoutQc):
        assert timeout_qc.view >= self.current_view
        self.overlay = Overlay()

    def build_timeout_qc(self, msgs: Set[Timeout]) -> TimeoutQc:
        pass

    def send(self, vote: Vote | Timeout | TimeoutQc, *ids: Id):
        pass

    def broadcast(self, block):
        pass

    def try_commit_grand_parent(self, block: Block):
        parent = self.safe_blocks.get(block.parent())
        grand_parent = self.safe_blocks.get(parent.parent())
        # this case should just trigger on genesis_case,
        # as the preconditions on outer calls should check on block validity
        if not parent or not grand_parent:
            return
        can_commit = (
                parent.view == (grand_parent.view + 1) and
                isinstance(block.qc, (StandardQc,)) and
                isinstance(parent.qc, (StandardQc,))
        )
        if can_commit:
            self.committed_blocks[grand_parent.id()] = grand_parent
            self.increment_latest_committed_view(grand_parent.view)

    def increment_voted_view(self, view: View):
        self.highest_voted_view = max(view, self.highest_voted_view)

    def increment_latest_committed_view(self, view: View):
        self.latest_committed_view = max(view, self.latest_committed_view)

    def increment_view_qc(self, qc: Qc) -> bool:
        if qc.view < self.current_view:
            return False
        self.last_timeout_view_qc = None
        self.current_view = qc.view + 1
        return True

    def increment_view_timeout_qc(self, timeout_qc: TimeoutQc):
        if timeout_qc is None or timeout_qc.view < self.current_view:
            return
        self.last_timeout_view_qc = timeout_qc
        self.current_view = self.last_timeout_view_qc.view + 1
        return True

    @staticmethod
    def get_max_timeout(timeouts: Set[Timeout]) -> Optional[Timeout]:
        if not timeouts:
            return None
        return max(timeouts, key=lambda time: time.qc.view)


if __name__ == "__main__":
    pass
