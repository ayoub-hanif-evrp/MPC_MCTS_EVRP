"""Opt-in measurement hooks; inactive during ordinary scientific runs."""

from collections import defaultdict
from time import perf_counter

ACTIVE = None


class Measurements:
    def __init__(self):
        self.seconds = defaultdict(float)
        self.counts = defaultdict(int)
        self.branches = []
        self.identical_unused = defaultdict(float)

    def __enter__(self):
        global ACTIVE
        if ACTIVE is not None:
            raise RuntimeError("Measurements cannot be nested")
        ACTIVE = self
        return self

    def __exit__(self, *args):
        global ACTIVE
        ACTIVE = None

    def report(self):
        return dict(seconds=dict(self.seconds), counts=dict(self.counts),
                    mean_branching=sum(self.branches) / len(self.branches) if self.branches else 0,
                    max_branching=max(self.branches, default=0),
                    identical_unused=dict(self.identical_unused))


def stamp():
    return perf_counter() if ACTIVE is not None else 0.0


def elapsed(name, start):
    if ACTIVE is not None:
        ACTIVE.seconds[name] += perf_counter() - start


def count(name, value=1):
    if ACTIVE is not None:
        ACTIVE.counts[name] += value


def branching(actions):
    if ACTIVE is not None:
        ACTIVE.branches.append(len(actions))
