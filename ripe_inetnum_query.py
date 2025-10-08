#!/usr/bin/env python3

import argparse
import ipaddress
import json
import sys
import requests
import time
import urllib.parse
from datetime import datetime


class IpRangeHunter:
    BASE_URL = "https://rest.db.ripe.net"

    def __init__(self, debug=False):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'RIPE-Inetnum-Query-Tool/1.0'
        })
        self.debug = debug

    def hunt_for_ranges(self, prefix):
        results = []

        if self.debug:
            print(f"DEBUG: Searching for inetnum records in {prefix}")

        try:
            self._do_the_magic_search(prefix, results)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)

        return results

    def _do_the_magic_search(self, prefix, results):
        if prefix.version == 4:
            start_ip = str(prefix.network_address)
            end_ip = str(prefix.broadcast_address)
            query_range = f"{start_ip} - {end_ip}"
            object_type = 'inetnum'
        else:
            query_range = str(prefix)
            object_type = 'inet6num'

        if self.debug:
            print(f"DEBUG: Querying range: {query_range}")

        self._ask_ripe_nicely(query_range, object_type, results)

    def _ask_ripe_nicely(self, query_range, object_type, results):
        try:
            url = f"{self.BASE_URL}/search.json"

            query_params = [
                f"query-string={urllib.parse.quote(query_range)}",
                f"type-filter={object_type}",
                "flags=all-more",
                "flags=no-referenced",
                "flags=no-irt",
                "source=RIPE"
            ]

            full_url = f"{url}?{'&'.join(query_params)}"

            if self.debug:
                print(f"DEBUG: Making request to: {full_url}")

            response = self.session.get(full_url)

            if self.debug:
                print(f"DEBUG: Response status: {response.status_code}")

            if response.status_code == 429:
                if self.debug:
                    print(f"DEBUG: Rate limited, waiting...")
                time.sleep(5)
                return

            if response.status_code == 404:
                if self.debug:
                    print(f"DEBUG: No results found for range {query_range}")
                return

            if response.status_code != 200:
                if self.debug:
                    print(f"DEBUG: API error: {response.status_code}")
                    print(f"DEBUG: Response: {response.text[:300]}")
                return

            data = response.json()

            if self.debug:
                obj_count = len(data.get('objects', {}).get('object', [])) if 'objects' in data else 0
                print(f"DEBUG: Found {obj_count} objects for range {query_range}")

            self._extract_goodies(data, results)

        except Exception as e:
            if self.debug:
                print(f"DEBUG: Error querying range {query_range}: {e}")

    def _extract_goodies(self, data, results):
        if 'objects' not in data or 'object' not in data['objects']:
            return

        objects = data['objects']['object']
        if not isinstance(objects, list):
            objects = [objects]

        for obj in objects:
            record = self._parse_ripe_object(obj)
            if record:
                if not any(existing.get('inetnum') == record.get('inetnum') for existing in results):
                    results.append(record)
                    if self.debug:
                        print(f"DEBUG: Added record: {record.get('inetnum')}")

    def _parse_ripe_object(self, obj):
        try:
            record = {}

            obj_type = obj.get('type')
            if obj_type not in ['inetnum', 'inet6num']:
                return None

            if 'primary-key' in obj and 'attribute' in obj['primary-key']:
                record['inetnum'] = obj['primary-key']['attribute'][0]['value']
            else:
                return None

            if 'attributes' in obj and 'attribute' in obj['attributes']:
                attributes = obj['attributes']['attribute']
                if not isinstance(attributes, list):
                    attributes = [attributes]

                for attr in attributes:
                    name = attr.get('name', '')
                    value = attr.get('value', '')

                    if name in ['netname', 'descr', 'country', 'org', 'admin-c', 'tech-c', 'status', 'mnt-by', 'created', 'last-modified']:
                        if name in record:
                            if isinstance(record[name], list):
                                record[name].append(value)
                            else:
                                record[name] = [record[name], value]
                        else:
                            record[name] = value

            return record

        except Exception:
            return None


def setup_args():
    parser = argparse.ArgumentParser(
        description='Query RIPE database for inetnum records within a prefix',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 192.168.1.0/24
  %(prog)s 2001:db8::/32
  %(prog)s --verbose 10.0.0.0/8
        """
    )

    parser.add_argument(
        'prefix',
        help='IP prefix to search (e.g., 192.168.1.0/24 or 2001:db8::/32)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output showing all object attributes'
    )

    parser.add_argument(
        '--format', '-f',
        choices=['table', 'json', 'csv'],
        default='table',
        help='Output format (default: table)'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug output to see API responses'
    )

    return parser.parse_args()


def check_prefix(prefix_str):
    try:
        return ipaddress.IPv4Network(prefix_str, strict=False)
    except ipaddress.AddressValueError:
        try:
            return ipaddress.IPv6Network(prefix_str, strict=False)
        except ipaddress.AddressValueError as e:
            raise ipaddress.AddressValueError(f"Invalid IP prefix '{prefix_str}': {e}")


def pretty_print_value(value):
    if isinstance(value, list):
        return ', '.join(str(v) for v in value)
    return str(value) if value else ''


def show_table_results(results, verbose=False):
    if not results:
        print("No inetnum records found within the specified prefix.")
        return

    print(f"\nFound {len(results)} inetnum record(s):\n")

    if verbose:
        for i, result in enumerate(results, 1):
            print(f"{'='*60}")
            print(f"Record {i}")
            print(f"{'='*60}")

            field_order = ['inetnum', 'netname', 'descr', 'country', 'org', 'admin-c', 'tech-c', 'status', 'mnt-by', 'created', 'last-modified']

            for field in field_order:
                value = result.get(field)
                if value:
                    formatted_value = pretty_print_value(value)
                    print(f"{field:15}: {formatted_value}")

            for key, value in result.items():
                if key not in field_order and value:
                    formatted_value = pretty_print_value(value)
                    print(f"{key:15}: {formatted_value}")
            print()
    else:
        headers = ['Inetnum Range', 'Netname', 'Description', 'Country', 'Status']
        col_widths = [35, 20, 40, 8, 15]

        header_line = ""
        separator_line = ""
        for header, width in zip(headers, col_widths):
            header_line += f"{header:<{width}} "
            separator_line += "-" * width + " "

        print(header_line)
        print(separator_line)

        for result in results:
            inetnum = pretty_print_value(result.get('inetnum', ''))[:col_widths[0]-1]
            netname = pretty_print_value(result.get('netname', ''))[:col_widths[1]-1]
            description = pretty_print_value(result.get('descr', ''))[:col_widths[2]-1]
            country = pretty_print_value(result.get('country', ''))[:col_widths[3]-1]
            status = pretty_print_value(result.get('status', ''))[:col_widths[4]-1]

            row_values = [inetnum, netname, description, country, status]
            row_line = ""
            for value, width in zip(row_values, col_widths):
                row_line += f"{value:<{width}} "

            print(row_line)


def show_json_results(results):
    if not results:
        print(json.dumps({"message": "No inetnum records found", "count": 0}, indent=2))
        return

    formatted_results = []
    for result in results:
        formatted_result = {}
        for key, value in result.items():
            formatted_result[key] = pretty_print_value(value)
        formatted_results.append(formatted_result)

    output = {
        "count": len(formatted_results),
        "timestamp": datetime.now().isoformat(),
        "records": formatted_results
    }

    print(json.dumps(output, indent=2))


def show_csv_results(results):
    import csv
    import io

    if not results:
        print("inetnum,netname,description,country,status")
        return

    all_fields = set()
    for result in results:
        all_fields.update(result.keys())

    fieldnames = sorted(all_fields)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)

    writer.writeheader()
    for result in results:
        formatted_row = {}
        for field in fieldnames:
            formatted_row[field] = pretty_print_value(result.get(field, ''))
        writer.writerow(formatted_row)

    print(output.getvalue().strip())


def main():
    args = setup_args()

    try:
        prefix = check_prefix(args.prefix)

        print(f"Querying RIPE database for inetnum records within {prefix}...")

        hunter = IpRangeHunter(debug=args.debug)
        results = hunter.hunt_for_ranges(prefix)

        if args.format == 'json':
            show_json_results(results)
        elif args.format == 'csv':
            show_csv_results(results)
        else:
            show_table_results(results, args.verbose)

    except ipaddress.AddressValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
