import component.litegraph as lg

_TITLE = lg._LG_TITLE_HEIGHT


def _graph():
    """infile -> a -> b -> c -> outfile, a -> c, two constants -> b, an unconnected constant, d with a position"""
    g = lg._GraphBuilder()
    infile = g.add_core_node("core/infile", None, {"name": "in", "version": "1"})
    a = g.add_node("parma/prepare:1", None, [("data", "file"), ("count", "int")], [("x", "file"), ("y", "file")], {})
    b = g.add_node("parma/train_a_model_with_long_name:3", None,
                   [("x", "file"), ("rate", "float"), ("label", "str")], [("model", "file")], {})
    c = g.add_node("parma/evaluate:1", None, [("model", "file"), ("y", "file")], [("report", "file")], {})
    rate = g.add_core_node("core/float", None, {"value": 0.1})
    label = g.add_core_node("core/str", None, {"value": "z"})
    outfile = g.add_core_node("core/outfile", None, {"name": "report"})
    lonely = g.add_core_node("core/int", None, {"value": 3})
    d = g.add_node("parma/other:1", [1234, 567], [], [], {})
    g.add_link(infile, 0, a, 0)
    g.add_link(a, 0, b, 0)
    g.add_link(rate, 0, b, 1)
    g.add_link(label, 0, b, 2)
    g.add_link(b, 0, c, 0)
    g.add_link(a, 1, c, 1)
    g.add_link(c, 0, outfile, 0)
    return g, {"infile": infile, "a": a, "b": b, "c": c, "rate": rate, "label": label, "outfile": outfile,
               "lonely": lonely, "d": d}


def _rect(lg_node):
    w, h = lg._estimated_size(lg_node)
    x, y = lg_node["pos"]
    return x, y - _TITLE, x + w, y + h


def test_all_nodes_placed_and_stored_position_kept():
    g, nodes = _graph()
    lg._LayeredLayout(g).apply()
    assert all(node["pos"] is not None for node in g.nodes)
    assert nodes["d"]["pos"] == [1234, 567]


def test_sources_left_of_readers():
    g, nodes = _graph()
    lg._LayeredLayout(g).apply()
    by_id = {node["id"]: node for node in g.nodes}
    for _, source, _, target, _, _ in g.links:
        source_right = _rect(by_id[source])[2]
        assert source_right + lg._LayeredLayout.H_GAP <= by_id[target]["pos"][0] + 0.1


def test_constants_in_column_directly_before_reader():
    g, nodes = _graph()
    lg._LayeredLayout(g).apply()
    assert nodes["rate"]["pos"][0] == nodes["a"]["pos"][0]
    assert nodes["label"]["pos"][0] == nodes["a"]["pos"][0]
    assert nodes["infile"]["pos"][0] == lg._LayeredLayout.LEFT


def test_no_overlap():
    g, nodes = _graph()
    lg._LayeredLayout(g).apply()
    auto = [node for node in g.nodes if node is not nodes["d"]]
    for i, first in enumerate(auto):
        for second in auto[i + 1:]:
            x1, y1, x2, y2 = _rect(first)
            u1, v1, u2, v2 = _rect(second)
            assert x2 <= u1 or u2 <= x1 or y2 <= v1 or v2 <= y1, (first["type"], second["type"])


def test_compact():
    g, nodes = _graph()
    lg._LayeredLayout(g).apply()
    auto = [node for node in g.nodes if node is not nodes["d"]]
    rects = [_rect(node) for node in auto]
    assert min(r[0] for r in rects) == lg._LayeredLayout.LEFT
    assert min(r[1] for r in rects) == lg._LayeredLayout.TOP - _TITLE
    # 4 columns: infile | a, rate, label, lonely | b | c | outfile -> far less than the former 520 px per column
    assert max(r[2] for r in rects) < 1400
    assert max(r[3] for r in rects) < 500


def test_estimated_size_like_litegraph():
    g, nodes = _graph()
    # a: 2 rows, title 15 chars -> width max(4*8.4 + 1*8.4 + 10, 126, 140) = 140, one widget (count) -> 210
    assert lg._estimated_size(nodes["a"]) == (210, 2 * 20 + 24 + 8)
    # infile: 1 row, 2 widgets starting at 25
    assert lg._estimated_size(nodes["infile"]) == (210, 25 + 2 * 24 + 8)
