from markdown_it import MarkdownIt


md = MarkdownIt("commonmark", {"html": True, "linkify": True})


def _convert_pipe_tables_to_html(markdown_text: str) -> str:
    """
    Minimal GitHub-style pipe table support.

    Supports blocks like:
      | A | B |
      |---|---|
      | 1 | 2 |
    """

    lines = markdown_text.splitlines()
    out: list[str] = []

    def is_pipe_row(s: str) -> bool:
        s = s.strip()
        return s.startswith("|") and s.endswith("|") and "|" in s[1:-1]

    def parse_cells(row: str) -> list[str]:
        parts = row.strip()[1:-1].split("|")
        return [p.strip() for p in parts]

    def is_separator_row(s: str, expected_cols: int) -> bool:
        s = s.strip()
        if not (s.startswith("|") and s.endswith("|")):
            return False
        cells = parse_cells(s)
        if len(cells) != expected_cols:
            return False
        for c in cells:
            c2 = c.replace(":", "").replace("-", "").strip()
            if c2:
                return False
        return True

    def align_for_sep_cell(sep_cell: str) -> str:
        s = sep_cell.strip()
        left = s.startswith(":")
        right = s.endswith(":")
        if left and right:
            return "center"
        if right:
            return "right"
        if left:
            return "left"
        return ""

    # markdown-it-py changed inline render API naming across versions:
    # renderInline(...) in most releases, render_inline(...) in some wrappers.
    render_inline_fn = getattr(md, "renderInline", None) or getattr(md, "render_inline", None)

    def cell_html(cell_text: str) -> str:
        cell_text = cell_text.replace("\n", "<br/>")
        if render_inline_fn is None:
            # Fallback: full render and trim wrapper paragraph if present.
            rendered = md.render(cell_text).strip()
            if rendered.startswith("<p>") and rendered.endswith("</p>"):
                return rendered[3:-4].strip()
            return rendered
        return render_inline_fn(cell_text).strip()

    i = 0
    while i < len(lines):
        line = lines[i]
        if not is_pipe_row(line):
            out.append(line)
            i += 1
            continue

        header_cells = parse_cells(line)
        if not header_cells or len(header_cells) < 2:
            out.append(line)
            i += 1
            continue

        if i + 1 >= len(lines) or not is_separator_row(lines[i + 1], len(header_cells)):
            out.append(line)
            i += 1
            continue

        sep_cells = parse_cells(lines[i + 1])
        aligns = [align_for_sep_cell(c) for c in sep_cells]
        i += 2

        body_rows: list[list[str]] = []
        while i < len(lines) and is_pipe_row(lines[i]):
            body_rows.append(parse_cells(lines[i]))
            i += 1

        def norm_row(row: list[str]) -> list[str]:
            row = row[: len(header_cells)]
            if len(row) < len(header_cells):
                row = row + [""] * (len(header_cells) - len(row))
            return row

        body_rows = [norm_row(r) for r in body_rows if r]

        thead_cells: list[str] = []
        for col_idx, h in enumerate(header_cells):
            align = aligns[col_idx] if col_idx < len(aligns) else ""
            style = f' style="text-align:{align};"' if align else ""
            thead_cells.append(f"<th{style}>{cell_html(h)}</th>")

        tbody_rows_html: list[str] = []
        for r in body_rows:
            tds = [f"<td>{cell_html(cell)}</td>" for cell in r]
            tbody_rows_html.append("<tr>" + "".join(tds) + "</tr>")

        out.append(
            "\n".join(
                [
                    '<table class="kb-table">',
                    "<thead><tr>" + "".join(thead_cells) + "</tr></thead>",
                    "<tbody>" + "".join(tbody_rows_html) + "</tbody>",
                    "</table>",
                ]
            )
        )

    return "\n".join(out)


def render_markdown(content: str) -> str:
    converted = _convert_pipe_tables_to_html(content)
    return md.render(converted)
