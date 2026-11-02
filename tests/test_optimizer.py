from services.optimizer import Supplier, optimize

S = [Supplier("A", 30, 200), Supplier("B", 20, 100, 50), Supplier("C", 0)]
P = {"A": {0: 10, 1: 5, 2: 8}, "B": {0: 9, 1: 6}, "C": {0: 12, 1: 4, 2: 9}}


def test_split_not_worse_than_single():
    r = optimize([10, 10, 5], S, P)
    assert r["split"].total <= r["single"].total
    assert r["split"].total == 195 and r["single"].total == 205


def test_min_order_excludes_supplier():
    r = optimize([1], [Supplier("B", 0, None, 50)], {"B": {0: 10}})
    assert r["single"] is None


def test_missing_reported():
    r = optimize([1, 1], [Supplier("A")], {"A": {0: 5}})
    assert r["single"].missing == [1]
