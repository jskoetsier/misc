#!/usr/bin/env python3
"""
RIPE Database Inetnum Query Tool

This script queries the RIPE database to find all inetnum records within a specified IP prefix.
It uses the RIPE REST API with the simple JSON endpoint format.

Usage:
    python ripe_inetnum_query.py <prefix>

Examples:
    python ripe_inetnum_query.py 192.168.1.0/24
    python ripe_inetnum_query.py 2001:db8::/32
"""

import argparse
import ipaddress
import json
import sys
import requests
import time
import urllib.parse
from typing import List, Dict, Union, Optional
from datetime import datetime


class RIPEQuery:
    """Class to handle RIPE database queries for inetnum records using simplified REST API."""

    BASE_URL = "https://rest.db.ripe.net"

    def __init__(self, debug=False):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'RIPE-Inetnum-Query-Tool/1.0'
        })
        self.debug = debug

    def search_inetnum_in_prefix(self, prefix: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]) -> List[Dict]:
        """
        Search for all inetnum records within the specified prefix.

        Args:
            prefix: The IP network prefix to search within

        Returns:
            List of inetnum records found within the prefix
        """
        results = []

        if self.debug:
            print(f"DEBUG: Searching for inetnum records in {prefix}")

        try:
            # Use the simpler approach with direct API calls
            self._search_with_simple_api(prefix, results)

        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)

        return results

    def _search_with_simple_api(self, prefix: Union[ipaddress.IPv4Network, ipaddress.IPv6Network], results: List[Dict]):
        """Search using the simple RIPE API format with single query."""

        # Convert prefix to range format
        if prefix.version == 4:
            start_ip = str(prefix.network_address)
            end_ip = str(prefix.broadcast_address)
            query_range = f"{start_ip} - {end_ip}"
            object_type = 'inetnum'
        else:
            # For IPv6, use CIDR notation
            query_range = str(prefix)
            object_type = 'inet6num'

        if self.debug:
            print(f"DEBUG: Querying range: {query_range}")

        self._query_range(query_range, object_type, results)

    def _generate_search_ranges(self, prefix: ipaddress.IPv4Network) -> List[str]:
        """Generate comprehensive IP ranges to search for within the prefix down to /30."""
        ranges = []

        # Start with the entire prefix range
        start_ip = prefix.network_address
        end_ip = prefix.broadcast_address
        ranges.append(f"{start_ip} - {end_ip}")

        # Generate all subnets down to /30 as originally requested
        max_prefix = min(30, prefix.prefixlen + 8)  # Don't go smaller than /30, limit search depth

        for target_prefix_len in range(prefix.prefixlen + 1, max_prefix + 1):
            try:
                subnets = list(prefix.subnets(new_prefix=target_prefix_len))

                # Limit the number of subnets per prefix length to avoid too many requests
                if target_prefix_len <= 24:
                    max_subnets = 50  # More subnets for larger blocks
                elif target_prefix_len <= 28:
                    max_subnets = 100  # Many subnets for medium blocks
                else:
                    max_subnets = 200  # Allow more for /29 and /30

                for subnet in subnets[:max_subnets]:
                    subnet_range = f"{subnet.network_address} - {subnet.broadcast_address}"
                    ranges.append(subnet_range)

                if self.debug and len(subnets) > max_subnets:
                    print(f"DEBUG: Limited /{target_prefix_len} subnets to {max_subnets} (total: {len(subnets)})")

            except ValueError:
                break  # No more subnets possible

        # Remove duplicates while preserving order
        seen = set()
        unique_ranges = []
        for r in ranges:
            if r not in seen:
                seen.add(r)
                unique_ranges.append(r)

        if self.debug:
            print(f"DEBUG: Generated {len(unique_ranges)} unique search ranges")

        return unique_ranges

    def _query_range(self, query_range: str, object_type: str, results: List[Dict]):
        """Query RIPE API for a specific IP range using the all-more flag."""

        try:
            # Use the exact format from the user's example: spaces in range, not hyphens
            # The all-more flag will return all more specific allocations within this range

            url = f"{self.BASE_URL}/search.json"

            # Build the URL with multiple flags as separate parameters
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

            # Process all objects from the response
            self._process_all_objects(data, results)

        except Exception as e:
            if self.debug:
                print(f"DEBUG: Error querying range {query_range}: {e}")

    def _process_all_objects(self, data: Dict, results: List[Dict]):
        """Process API response and extract all inetnum records."""

        if 'objects' not in data or 'object' not in data['objects']:
            return

        objects = data['objects']['object']
        if not isinstance(objects, list):
            objects = [objects]

        for obj in objects:
            record = self._extract_record_from_object(obj)
            if record:
                # Check for duplicates
                if not any(existing.get('inetnum') == record.get('inetnum') for existing in results):
                    results.append(record)
                    if self.debug:
                        print(f"DEBUG: Added record: {record.get('inetnum')}")

    def _search_ipv6_ranges(self, prefix: ipaddress.IPv6Network, results: List[Dict]):
        """Search for IPv6 inet6num records."""

        # For IPv6, use the prefix directly
        prefix_str = str(prefix)

        if self.debug:
            print(f"DEBUG: Querying IPv6 prefix: {prefix_str}")

        try:
            url = f"{self.BASE_URL}/search.json"
            params = {
                'query-string': prefix_str,
                'type-filter': 'inet6num',
                'flags': 'all-more',
                'flags': 'no-referenced',
                'flags': 'no-irt',
                'source': 'RIPE'
            }

            response = self.session.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                self._process_response_objects(data, prefix, results)
            elif self.debug:
                print(f"DEBUG: IPv6 query failed with status {response.status_code}")

        except Exception as e:
            if self.debug:
                print(f"DEBUG: Error in IPv6 search: {e}")

    def _process_response_objects(self, data: Dict, target_prefix: Union[ipaddress.IPv4Network, ipaddress.IPv6Network],
                                 results: List[Dict]):
        """Process API response and extract inetnum records."""

        if 'objects' not in data or 'object' not in data['objects']:
            return

        objects = data['objects']['object']
        if not isinstance(objects, list):
            objects = [objects]

        for obj in objects:
            record = self._extract_record_from_object(obj)
            if record and self._record_in_prefix(record, target_prefix):
                # Check for duplicates
                if not any(existing.get('inetnum') == record.get('inetnum') for existing in results):
                    results.append(record)
                    if self.debug:
                        print(f"DEBUG: Added record: {record.get('inetnum')}")

    def _extract_record_from_object(self, obj: Dict) -> Optional[Dict]:
        """Extract record information from a RIPE object."""

        try:
            record = {}

            # Get object type
            obj_type = obj.get('type')
            if obj_type not in ['inetnum', 'inet6num']:
                return None

            # Get primary key (the inetnum range)
            if 'primary-key' in obj and 'attribute' in obj['primary-key']:
                record['inetnum'] = obj['primary-key']['attribute'][0]['value']
            else:
                return None

            # Extract attributes
            if 'attributes' in obj and 'attribute' in obj['attributes']:
                attributes = obj['attributes']['attribute']
                if not isinstance(attributes, list):
                    attributes = [attributes]

                for attr in attributes:
                    name = attr.get('name', '')
                    value = attr.get('value', '')

                    if name in ['netname', 'descr', 'country', 'org', 'admin-c', 'tech-c', 'status', 'mnt-by', 'created', 'last-modified']:
                        if name in record:
                            # Handle multiple values
                            if isinstance(record[name], list):
                                record[name].append(value)
                            else:
                                record[name] = [record[name], value]
                        else:
                            record[name] = value

            return record

        except Exception:
            return None

    def _record_in_prefix(self, record: Dict, target_prefix: Union[ipaddress.IPv4Network, ipaddress.IPv6Network]) -> bool:
        """Check if a record overlaps with or is contained within the target prefix."""

        try:
            inetnum_str = record.get('inetnum', '')

            if target_prefix.version == 4:
                # IPv4 format: "192.168.1.0 - 192.168.1.255"
                if ' - ' in inetnum_str:
                    start_str, end_str = inetnum_str.split(' - ')
                    start_ip = ipaddress.IPv4Address(start_str.strip())
                    end_ip = ipaddress.IPv4Address(end_str.strip())

                    # Check if there's any overlap with target prefix
                    return not (end_ip < target_prefix.network_address or
                              start_ip > target_prefix.broadcast_address)
                else:
                    # Try as CIDR notation
                    try:
                        network = ipaddress.IPv4Network(inetnum_str, strict=False)
                        return network.overlaps(target_prefix)
                    except ipaddress.AddressValueError:
                        return False
            else:
                # IPv6 format: "2001:db8::/32"
                try:
                    network = ipaddress.IPv6Network(inetnum_str, strict=False)
                    return network.overlaps(target_prefix)
                except ipaddress.AddressValueError:
                    return False

        except (ipaddress.AddressValueError, ValueError):
            return False

        return False


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Query RIPE database for inetnum records within a prefix',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 192.168.1.0/24     # Query IPv4 prefix
  %(prog)s 2001:db8::/32      # Query IPv6 prefix
  %(prog)s --verbose 10.0.0.0/8  # Verbose output
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


def validate_prefix(prefix_str: str) -> Union[ipaddress.IPv4Network, ipaddress.IPv6Network]:
    """
    Validate and parse the IP prefix string.

    Args:
        prefix_str: String representation of the IP prefix

    Returns:
        Parsed IP network object

    Raises:
        ipaddress.AddressValueError: If the prefix is invalid
    """
    try:
        # Try IPv4 first
        return ipaddress.IPv4Network(prefix_str, strict=False)
    except ipaddress.AddressValueError:
        try:
            # Try IPv6
            return ipaddress.IPv6Network(prefix_str, strict=False)
        except ipaddress.AddressValueError as e:
            raise ipaddress.AddressValueError(f"Invalid IP prefix '{prefix_str}': {e}")


def format_field_value(value):
    """Format field values that might be lists."""
    if isinstance(value, list):
        return ', '.join(str(v) for v in value)
    return str(value) if value else ''


def format_output_table(results: List[Dict], verbose: bool = False):
    """Format results as a nicely formatted table."""
    if not results:
        print("No inetnum records found within the specified prefix.")
        return

    print(f"\nFound {len(results)} inetnum record(s):\n")

    if verbose:
        # Detailed view with all attributes
        for i, result in enumerate(results, 1):
            print(f"{'='*60}")
            print(f"Record {i}")
            print(f"{'='*60}")

            # Display in a nice order
            field_order = ['inetnum', 'netname', 'descr', 'country', 'org', 'admin-c', 'tech-c', 'status', 'mnt-by', 'created', 'last-modified']

            for field in field_order:
                value = result.get(field)
                if value:
                    formatted_value = format_field_value(value)
                    print(f"{field:15}: {formatted_value}")

            # Show any other fields not in the standard order
            for key, value in result.items():
                if key not in field_order and value:
                    formatted_value = format_field_value(value)
                    print(f"{key:15}: {formatted_value}")
            print()
    else:
        # Compact table view with better formatting
        headers = ['Inetnum Range', 'Netname', 'Description', 'Country', 'Status']
        col_widths = [35, 20, 40, 8, 15]

        # Print header
        header_line = ""
        separator_line = ""
        for header, width in zip(headers, col_widths):
            header_line += f"{header:<{width}} "
            separator_line += "-" * width + " "

        print(header_line)
        print(separator_line)

        # Print data rows
        for result in results:
            inetnum = format_field_value(result.get('inetnum', ''))[:col_widths[0]-1]
            netname = format_field_value(result.get('netname', ''))[:col_widths[1]-1]
            description = format_field_value(result.get('descr', ''))[:col_widths[2]-1]
            country = format_field_value(result.get('country', ''))[:col_widths[3]-1]
            status = format_field_value(result.get('status', ''))[:col_widths[4]-1]

            row_values = [inetnum, netname, description, country, status]
            row_line = ""
            for value, width in zip(row_values, col_widths):
                row_line += f"{value:<{width}} "

            print(row_line)


def format_output_json(results: List[Dict]):
    """Format results as JSON."""
    if not results:
        print(json.dumps({"message": "No inetnum records found", "count": 0}, indent=2))
        return

    # Convert any list values to comma-separated strings for JSON output
    formatted_results = []
    for result in results:
        formatted_result = {}
        for key, value in result.items():
            formatted_result[key] = format_field_value(value)
        formatted_results.append(formatted_result)

    output = {
        "count": len(formatted_results),
        "timestamp": datetime.now().isoformat(),
        "records": formatted_results
    }

    print(json.dumps(output, indent=2))


def format_output_csv(results: List[Dict]):
    """Format results as CSV."""
    import csv
    import io

    if not results:
        print("inetnum,netname,description,country,status")
        return

    # Get all possible field names
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
            formatted_row[field] = format_field_value(result.get(field, ''))
        writer.writerow(formatted_row)

    print(output.getvalue().strip())


def main():
    """Main function."""
    args = parse_arguments()

    try:
        # Validate the prefix
        prefix = validate_prefix(args.prefix)

        print(f"Querying RIPE database for inetnum records within {prefix}...")

        # Create RIPE query object and search
        ripe_query = RIPEQuery(debug=args.debug)
        results = ripe_query.search_inetnum_in_prefix(prefix)

        # Format and display results
        if args.format == 'json':
            format_output_json(results)
        elif args.format == 'csv':
            format_output_csv(results)
        else:  # table format
            format_output_table(results, args.verbose)

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
