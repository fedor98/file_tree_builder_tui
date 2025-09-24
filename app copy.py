def checkbox_label(selected: bool, path: Path) -> Text:
    """Create a colored radio-label as a Rich Text renderable."""
    show_icon = path != ROOT  # hide the circle on the root only
    t = Text()
    if selected:
        if show_icon:
            t.append(_radio_icon(True), style=f"bold {SELECT_COLOR}")
            t.append(" ")
        t.append(path.name, style=f"bold {SELECT_COLOR}")
    else:
        if show_icon:
            t.append(_radio_icon(False), style=f"{UNSELECT_COLOR}")
            t.append(" ")
        t.append(path.name, style=f"{UNSELECT_COLOR}")
    return t
