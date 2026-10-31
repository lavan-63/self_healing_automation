"""One-round-trip DOM capture, limited to elements that carry an id.

Everything else (tag, text, class, ancestors, neighbours) is captured as context
so an element can still be recognised after its id changes.
"""
import hashlib
import re

CAPTURE_JS = r"""
const clean = s => (s || '').replace(/\s+/g, ' ').trim().slice(0, 60);
const sig = e => {
  if (!e) return '';
  const c = typeof e.className === 'string' ? e.className.trim().replace(/\s+/g, '.') : '';
  return e.tagName.toLowerCase() + (c ? '.' + c : '');
};
const leafText = e => (e.querySelectorAll('*').length <= 3 && !/^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName))
  ? clean(e.textContent) : '';
const ancestors = e => {
  const p = [];
  for (let n = e.parentElement; n && n.tagName !== 'HTML'; n = n.parentElement) p.unshift(sig(n));
  return p;
};
const context = e => {
  for (let p = e.parentElement; p; p = p.parentElement) {
    const h = p.querySelector('h1,h2,h3,h4,h5,h6,legend');
    if (h && !h.contains(e)) return clean(h.textContent);
  }
  return '';
};
const neighbour = n => n ? sig(n) + '|' + leafText(n) : '';
return Array.from(document.querySelectorAll('[id]')).map(e => ({
  id: e.id,
  tag: e.tagName.toLowerCase(),
  type: e.getAttribute('type') || '',
  name: e.getAttribute('name') || '',
  cls: typeof e.className === 'string' ? e.className.trim() : '',
  text: leafText(e),
  label: (e.labels && e.labels.length) ? clean(e.labels[0].textContent) : '',
  placeholder: e.getAttribute('placeholder') || '',
  role: [e.getAttribute('role'), e.getAttribute('aria-label')].filter(Boolean).join('|'),
  href: e.getAttribute('href') || '',
  ctx: context(e),
  path: ancestors(e),
  prev: neighbour(e.previousElementSibling),
  next: neighbour(e.nextElementSibling),
  visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length),
}));
"""

_VOLATILE = ("id", "visible")


def capture(driver):
    """Return a list of element dicts, one per [id] element, in a single browser call."""
    return driver.execute_script(CAPTURE_JS)


def fingerprint(element):
    """The part of a captured element that is stored in the repository (no id, no volatile state)."""
    return {k: v for k, v in element.items() if k not in _VOLATILE}


def id_template(element_id):
    """'react-select-3-input' -> 'react-select-#-input': ids that only differ by a counter share a template."""
    return re.sub(r"\d+", "#", element_id)


def dom_hash(elements):
    """Cheap page signature: changes whenever the set of ids changes."""
    return hashlib.sha1("|".join(sorted(e["id"] for e in elements)).encode()).hexdigest()[:12]
