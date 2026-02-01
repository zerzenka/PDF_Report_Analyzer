def find_ops_anchors(
    page,
    name_label: str = "NAME",
    id_label: str = "SA ID",
    top_ratio: float = 0.70
):
    """
    Find printed NAME and SA ID column headers on the Operations A3 form.

    Returns:
        (name_anchor, id_anchor)

    Each anchor is a pdfplumber word dict with:
        x0, x1, top, bottom, text
    """

    words = page.extract_words(use_text_flow=True)

    name_anchor = None
    id_anchor = None

    # Only search near top of page (safety)
    top_limit = page.height * float(top_ratio)

    for w in words:
        txt = w["text"].strip().upper()

        # Ignore anything too low on the page (likely handwriting)
        if w["top"] > top_limit:
            continue

        if name_label in txt and name_anchor is None:
            name_anchor = w

        # SA ID may come as "SA ID" or just "SA"
        if ("SA" in txt and "ID" in txt) and id_anchor is None:
            id_anchor = w

    if not name_anchor or not id_anchor:
    raise ValueError("Could not detect NAME / SA ID anchors on this page")

    print("FOUND NAME:", name_anchor)
    print("FOUND SA ID:", id_anchor)
    print("PAGE WIDTH:", page.width)

    return name_anchor, id_anchor
