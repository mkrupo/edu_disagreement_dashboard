"""Parse UTF-8 annotation files without trimming or normalizing EDU content."""

from os import PathLike

from .models import ParsedEDU


def parse_annotation(path: str | PathLike[str]) -> tuple[ParsedEDU, ...]:
    """Read non-empty lines as EDUs, preserving their source line numbers."""
    edus = []
    with open(path, encoding="utf-8", newline=None) as annotation:
        for line_number, line in enumerate(annotation, start=1):
            # Universal-newline handling has translated each terminator to LF.
            text = line.removesuffix("\n")
            if text != "":
                edus.append(ParsedEDU(len(edus), text, line_number))
    return tuple(edus)


def reconstruct_text(edus: tuple[ParsedEDU, ...]) -> str:
    """Concatenate EDU contents exactly, adding no separator."""
    return "".join(edu.text for edu in edus)
