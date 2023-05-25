import random
from abc import abstractmethod
from typing import Set, Optional, List
from carnot import Overlay, Id, Committee, View


class EntropyOverlay(Overlay):
    @abstractmethod
    def set_entropy(self, entropy: bytes):
        pass


class FlatOverlay(EntropyOverlay):
    def set_entropy(self, entropy: bytes):
        self.entropy = entropy

    def is_leader(self, _id: Id):
        return _id == self.leader()

    def leader(self) -> Id:
        random.seed(a=self.entropy, version=2)
        return random.choice(self.nodes)

    def is_member_of_leaf_committee(self, _id: Id) -> bool:
        return True

    def is_member_of_root_committee(self, _id: Id) -> bool:
        return True

    def is_member_of_child_committee(self, parent: Id, child: Id) -> bool:
        return False

    def parent_committee(self, _id: Id) -> Optional[Committee]:
        return None

    def leaf_committees(self) -> Set[Committee]:
        return {frozenset(self.nodes)}

    def root_committee(self) -> Committee:
        return set(self.nodes)

    def is_child_of_root_committee(self, _id: Id) -> bool:
        return True

    def leader_super_majority_threshold(self, _id: Id) -> int:
        return ((len(self.nodes) * 2) // 3) + 1

    def super_majority_threshold(self, _id: Id) -> int:
        return 0

    def __init__(self, nodes: List[Id]):
        self.nodes = nodes
        self.entropy = None


