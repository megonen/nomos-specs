# typing imports
from dataclasses import dataclass
from random import randint
from typing import TypeAlias

# carnot imports
# lib imports
from blspy import PrivateKey, Util, PopSchemeMPL, G2Element, G1Element

# stdlib imports
from hashlib import sha256

View: TypeAlias = int
Beacon: TypeAlias = bytes
Proof: TypeAlias = bytes  # For now this is gonna be a public key, in future research we may pivot to zk proofs.


def generate_random_sk() -> PrivateKey:
    seed = bytes([randint(0, 255) for _ in range(32)])
    return PopSchemeMPL.key_gen(seed)


@dataclass
class RandomBeacon:
    version: int
    context: View
    entropy: Beacon
    # TODO: Just the happy path beacons owns a proof, we can set the proof to empty bytes for now.
    # Probably we should separate this into two kinds of beacons and group them under a single type later on.
    proof: Proof


class NormalMode:

    @staticmethod
    def verify(beacon: RandomBeacon) -> bool:
        """
        :param proof: BLS signature
        :param beacon: Beacon is signature for current view
        :param view: View to verify beacon upon
        :return:
        """
        # TODO: Actually verify that the message is propoerly signed
        sig = G2Element.from_bytes(beacon.entropy)
        proof = G1Element.from_bytes(beacon.proof)
        return PopSchemeMPL.verify(proof, Util.hash256(str(beacon.context).encode()), sig)

    @staticmethod
    def generate_beacon(private_key: PrivateKey, view: View) -> Beacon:
        return bytes(PopSchemeMPL.sign(private_key, Util.hash256(str(view).encode())))


class RecoveryMode:

    @staticmethod
    def verify(last_beacon: RandomBeacon, beacon: RandomBeacon) -> bool:
        """
        :param last_beacon: Unhappy -> last working beacon (signature), Happy -> Hash of previous beacon and next view number
        :param beacon:
        :param view:
        :return:
        """
        b = sha256(last_beacon.entropy + str(beacon.context).encode()).digest()
        return b == beacon.entropy

    @staticmethod
    def generate_beacon(last_beacon: Beacon, view: View) -> Beacon:
        return sha256(last_beacon + str(view).encode()).digest()


class RandomBeaconHandler:
    def __init__(self, beacon: RandomBeacon):
        """
        :param beacon: Beacon should be initialized with either the last known working beacon from recovery.
        Or the hash of the genesis block in case of first consensus round.
        :return: Self
        """
        self.last_beacon: RandomBeacon = beacon

    def verify_happy(self, new_beacon: RandomBeacon) -> bool:
        if NormalMode.verify(new_beacon):
            self.last_beacon = new_beacon
            return True
        return False

    def verify_unhappy(self, new_beacon: RandomBeacon) -> bool:
        if RecoveryMode.verify(self.last_beacon, new_beacon):
            self.last_beacon = new_beacon
            return True
        return False
