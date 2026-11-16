"""Check a database file from the command line.

    python -m lca4pd.databases inspect FILE [--protocol ID]

Prints what the tool would read from the file. If the format is not
recognised, prints the file's headings (no data) to help adjust a protocol.
"""

import argparse
import sys

from . import ProtocolMismatch, describe_headings, load_protocols, read_file
from .reader import find_layout
from ..method import ef31


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lca4pd.databases")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="show what would be read from a database file")
    inspect.add_argument("file")
    inspect.add_argument("--protocol", help="force a format instead of recognising it")
    args = parser.parse_args(argv)

    try:
        parsed = read_file(args.file, args.protocol)
    except ProtocolMismatch as error:
        print(f"Not readable: {error}\n")
        if not args.file.lower().endswith(".ods"):
            for protocol in load_protocols().values():
                try:
                    find_layout(args.file, protocol)
                except ProtocolMismatch as reason:
                    print(f"- {protocol.id}: {reason}")
            print("\nHeadings in the file (no data):\n" + describe_headings(args.file))
        return 1

    report = parsed.report
    print(f"Format:   {report.protocol}")
    print(f"Sheet:    {report.sheet}")
    print(f"Version:  {report.version or '(not stated in the file)'}")
    print(f"Datasets: {report.datasets}")
    print("Share of datasets with a non-zero value:")
    for category in ef31.CATEGORIES:
        print(f"  {category.name:36s} {report.coverage[category.id]:6.1%}")
    for level, text in report.messages:
        print(f"[{level}] {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
