#!/usr/bin/env bash
# Render a project Markdown document to PDF, diagrams included.
#
#   tools/md2pdf.sh docs/superpowers/specs/2026-09-21-mechanical-design.md
#
# Writes the PDF next to the source file. Relative image paths (SVG or raster)
# resolve against the source file's directory, so figures come through.
#
# Needs: pandoc and weasyprint (brew install pandoc weasyprint).

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <file.md> [output.pdf]" >&2
    exit 64
fi

src=$1
if [ ! -f "$src" ]; then
    echo "$0: no such file: $src" >&2
    exit 66
fi

for tool in pandoc weasyprint; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "$0: $tool not found. brew install $tool" >&2
        exit 69
    }
done

repo_root=$(cd "$(dirname "$0")/.." && pwd)
css="$repo_root/tools/spec.css"
src_dir=$(cd "$(dirname "$src")" && pwd)
out=${2:-"${src%.md}.pdf"}
html=$(mktemp -t md2pdf).html

# Wrap pandoc's fragment ourselves: --standalone would print the title twice,
# once from the metadata block and once from the document's own H1.
{
    printf '<!DOCTYPE html><html><head><meta charset="utf-8">'
    printf '<link rel="stylesheet" href="%s"></head><body>\n' "$css"
    pandoc "$src" -f gfm -t html5
    printf '\n</body></html>\n'
} > "$html"

# --base-url lets WeasyPrint resolve the document's relative image paths.
weasyprint --base-url "$src_dir/" "$html" "$out"
rm -f "$html"

echo "wrote $out"
