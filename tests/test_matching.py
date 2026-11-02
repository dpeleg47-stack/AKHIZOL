from services.matching import Candidate, best_match, parse_size


def test_parse_size():
    assert parse_size("1.5L") == ("ml", 1500)
    assert parse_size("6x1.5L") == ("ml", 9000)
    assert parse_size('2 ק"ג') == ("g", 2000)
    assert parse_size("500 גרם") == ("g", 500)
    assert parse_size("молоко") is None


def test_picks_same_size_and_cheapest():
    item = {"name": "молоко", "name_he": "חלב", "brand": "תנובה", "size": "1 ליטר"}
    cands = [
        Candidate("חלב תנובה 3% 1 ליטר", 7.5),
        Candidate("חלב תנובה 3% 1 ליטר", 6.9),
        Candidate("חלב תנובה 3% 2 ליטר", 4.0),  # другая фасовка
    ]
    m = best_match(item, cands)
    assert m and m.candidate.unit_price == 6.9


def test_no_match_for_unrelated():
    assert best_match({"name_he": "חלב"}, [Candidate("שוקולד מריר", 5)]) is None


def test_barcode_wins():
    m = best_match({"name": "x", "barcode": "123"}, [Candidate("something else", 3, barcode="123")])
    assert m and m.score == 1.0
