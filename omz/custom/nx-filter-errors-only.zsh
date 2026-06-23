#!/bin/zsh
# Filter ESLint output to show only errors (remove warnings),
# remove file paths that have no errors beneath them,
# and collapse multiple blank lines to at most one empty line
#
# Usage: nx-filter-errors input.txt > output.txt
#    or: nx-filter-errors input.txt output.txt

nx-filter-errors() {
    local INPUT="${1:--}"
    local OUTPUT="${2:-/dev/stdout}"

    awk '
BEGIN { filepath = ""; errors = ""; has_error = 0 }

/^\/Users\// {
    if (filepath && has_error) {
        print filepath
        print errors
    }
    filepath = $0
    errors = ""
    has_error = 0
    next
}

/^[[:space:]]+[0-9]+:[0-9]+[[:space:]]+(error|warning)/ {
    if ($2 == "error") {
        errors = errors $0 "\n"
        has_error = 1
    }
    next
}

{
    if (filepath && has_error) {
        print filepath
        print errors
    }
    filepath = ""
    errors = ""
    has_error = 0
    print
}

END {
    if (filepath && has_error) {
        print filepath
        print errors
    }
}
' "$INPUT" | awk '
# Collapse multiple blank lines to max 2 (one empty line)
{
    if (/^[[:space:]]*$/) {
        blank_count++
    } else {
        if (blank_count > 0) {
            # Print at most 2 blank lines
            for (i = 0; i < (blank_count > 2 ? 2 : blank_count); i++) {
                print ""
            }
        }
        blank_count = 0
        print
    }
}
END {
    if (blank_count > 0) {
        for (i = 0; i < (blank_count > 2 ? 2 : blank_count); i++) {
            print ""
        }
    }
}
' > "$OUTPUT"
}

alias nxfilter="nx-filter-errors"
