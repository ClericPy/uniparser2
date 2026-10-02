"""``xpath`` operator (design doc 02 §6.11): the XML home ground.

The slots are ``["xpath", accessor, XPath]`` (the accessor first, the expression second; ``expr`` /
``ns`` written together as an object take slot 3).

Three measured facts are pinned here:

1. **A default namespace is a silent trap**: in ``<urlset xmlns="...">`` (a sitemap) ``//loc``
   returns empty **without reporting an error**, so the operator has to call that out in ``Missing``
   and offer the two fixes, ``local-name()`` and ``ns``;
2. **An undefined prefix is a compile-time error**: lxml raises ``XPathEvalError`` while
   constructing ⇒ ``UP2-E1005``;
3. **Attributes are strings directly** (``//enclosure/@url``), hence there is no ``@attribute``
   action, and ``nodes`` receiving a string must report ``UP2-E2002`` and point at ``text``.
"""

from __future__ import annotations

from typing import Any

import pytest

from uniparser2 import (
    Failed,
    Missing,
    Ok,
    Opaque,
    Outcome,
    Up2Error,
    compile_field,
    eval_field,
    pack,
)
from uniparser2.core import registry
from uniparser2.ops import xmlxpath

COVERS_PAIRS = (("xpath", "text"), ("xpath", "nodes"), ("xpath", "self"))

SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
DC_NS = "http://purl.org/dc/elements/1.1/"

SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="{SM_NS}">
  <url><loc>https://x/1</loc><lastmod>2026-09-01</lastmod></url>
  <url><loc>https://x/2</loc><lastmod>2026-09-02</lastmod></url>
</urlset>"""

RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="{DC_NS}">
  <channel>
    <item>
      <title>Title</title>
      <dc:creator>Reporter A</dc:creator>
      <enclosure url="https://x/a.mp3" type="audio/mpeg"/>
      <description><![CDATA[<p>body</p>]]></description>
    </item>
  </channel>
</rss>"""

NS_DC = {"dc": DC_NS}
NS_SM = {"sm": SM_NS}


def _no_missing_deps(instance: object, action: str) -> tuple[str, ...]:
    del instance, action
    return ()


@pytest.fixture
def xml_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """lxml is installed; only the dependency gate is bypassed, so the logic cases also run here."""
    monkeypatch.setattr(registry, "action_missing_deps", _no_missing_deps)


def run(chain: Any, value: Any = SITEMAP) -> Outcome:
    return eval_field(compile_field(chain), value)


def test_text_returns_list_of_element_text(xml_ready: None) -> None:
    assert run([["xpath", "text", "//title"]], RSS) == Ok(["Title"])


def test_text_on_attributes_needs_no_attr_action(xml_ready: None) -> None:
    """XPath can fetch attributes by itself — this is where it beats CSS.

    That is why there is no ``@attribute`` action.
    """
    assert run([["xpath", "text", "//enclosure/@url"]], RSS) == Ok(["https://x/a.mp3"])


def test_prefixed_namespace_with_ns_map(xml_ready: None) -> None:
    """A prefixed namespace must come with an ``ns`` map (selectolax reports Bad CSS Selectors)."""
    chain = [["xpath", "text", {"expr": "//dc:creator", "ns": NS_DC}]]
    assert run(chain, RSS) == Ok(["Reporter A"])


def test_undefined_prefix_is_compile_time_error(xml_ready: None) -> None:
    """lxml reports Undefined namespace prefix while **constructing** ⇒ compile-time E1005."""
    with pytest.raises(Up2Error) as info:
        compile_field([["xpath", "text", "//dc:creator"]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert "ns" in info.value.diagnostic.fix


def test_default_namespace_is_silently_empty_but_explained(xml_ready: None) -> None:
    """The classic sitemap trap: ``//loc`` silently returns empty.

    The diagnostic has to explain the default namespace.
    """
    outcome = run([["xpath", "text", "//loc"]])
    assert isinstance(outcome, Missing)
    assert SM_NS in outcome.reason
    assert "local-name()" in outcome.reason


def test_default_namespace_workarounds(xml_ready: None) -> None:
    by_local_name = [["xpath", "text", "//*[local-name()='loc']"]]
    by_ns_map = [["xpath", "text", {"expr": "//sm:loc", "ns": NS_SM}]]
    assert run(by_local_name) == Ok(["https://x/1", "https://x/2"])
    assert run(by_ns_map) == Ok(["https://x/1", "https://x/2"])


def test_cdata_text_is_intact(xml_ready: None) -> None:
    assert run([["xpath", "text", "//description"]], RSS) == Ok(["<p>body</p>"])


def test_case_sensitive_tag_names(xml_ready: None) -> None:
    """XML is case sensitive: ``//Title`` and ``//title`` are two different elements."""
    assert run([["xpath", "text", "//title"]], RSS) == Ok(["Title"])
    assert isinstance(run([["xpath", "text", "//Title"]], RSS), Missing)


def test_nodes_returns_opaque_list(xml_ready: None) -> None:
    # Use local-name(): the sitemap carries a default namespace, so ``//url`` silently finds nothing
    # (see the case above).
    outcome = run([["xpath", "nodes", "//*[local-name()='url']"]])
    assert isinstance(outcome, Ok)
    assert len(outcome.value) == 2
    assert all(isinstance(node, Opaque) for node in outcome.value)
    packed = pack(outcome.value)
    assert isinstance(packed, Failed)
    assert packed.code == "UP2-E2003"


def test_nodes_on_attribute_result_is_type_failure(xml_ready: None) -> None:
    outcome = run([["xpath", "nodes", "//enclosure/@url"]], RSS)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"
    assert "text" in outcome.fix


def test_self_then_relative_path(xml_ready: None) -> None:
    """``self`` takes one node, after which a relative path can keep selecting.

    This is the only way within L1 to "land on a single node".
    """
    chain = [["xpath", "self", {"expr": "//item", "ns": NS_DC}], ["xpath", "text", "./title"]]
    assert run(chain, RSS) == Ok(["Title"])


def test_self_on_attribute_result_is_type_failure(xml_ready: None) -> None:
    outcome = run([["xpath", "self", "//enclosure/@url"]], RSS)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_unknown_action_is_e1002(xml_ready: None) -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["xpath", "get", "//title"]])
    assert info.value.diagnostic.code == "UP2-E1002"


@pytest.mark.parametrize("expr", ["//[", "//a[", ""])
def test_bad_expression_is_schema_error(xml_ready: None, expr: str) -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["xpath", "text", expr]])
    assert info.value.diagnostic.code == "UP2-E1005"


def test_ns_must_be_string_map(xml_ready: None) -> None:
    with pytest.raises(Up2Error) as info:
        compile_field([["xpath", "text", {"expr": "//dc:creator", "ns": {"dc": 1}}]])
    assert info.value.diagnostic.code == "UP2-E1005"
    assert "ns" in info.value.diagnostic.message


def test_malformed_xml_is_e2005(xml_ready: None) -> None:
    outcome = run([["xpath", "text", "//title"]], "<html><br></html>")
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2005"
    assert "css" in outcome.fix


def test_list_input_is_type_failure(xml_ready: None) -> None:
    outcome = run([["xpath", "text", "//title"]], [1, 2])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_non_text_non_node_input_is_type_failure(xml_ready: None) -> None:
    outcome = run([["xpath", "text", "//title"]], 42)
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E2002"


def test_missing_lxml_reports_e1107(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise ImportError("no lxml")

    monkeypatch.setattr(registry, "action_missing_deps", _no_missing_deps)
    monkeypatch.setattr(xmlxpath, "_import_lxml", boom)
    outcome = run([["xpath", "text", "//title"]])
    assert isinstance(outcome, Failed)
    assert outcome.code == "UP2-E1107"
    assert "uniparser2[xml]" in outcome.fix


def test_missing_lxml_makes_op_unavailable_at_compile_time() -> None:
    xpath = registry.get("xpath")
    assert xpath is not None
    if not registry.op_missing_deps(xpath):
        pytest.skip("lxml is installed on this machine")
    with pytest.raises(Up2Error) as info:
        compile_field([["xpath", "text", "//title"]])
    assert info.value.diagnostic.code == "UP2-E1107"
    assert any("uniparser2[xml]" in hint for hint in info.value.diagnostic.allowed)


def test_real_lxml_roundtrip() -> None:
    """Walk the three most representative chains again under the real lxml (runs when installed)."""
    pytest.importorskip("lxml")
    assert run([["xpath", "text", "//*[local-name()='loc']"]]) == Ok(["https://x/1", "https://x/2"])
    assert run([["xpath", "text", {"expr": "//dc:creator", "ns": NS_DC}]], RSS) == Ok(
        ["Reporter A"]
    )
    assert run([["xpath", "text", "//enclosure/@url"]], RSS) == Ok(["https://x/a.mp3"])
