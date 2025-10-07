#!/usr/bin/perl
################################################################################
#
# cgrep.pl - Enhanced channel user search for IRSSI
#
# USAGE:
#   /cgrep <regexp>     - Search for users matching regexp
#   /cgrep_help         - Show help and available settings
#   /cgrep_stats        - Show search statistics
#
# DESCRIPTION:
#   Shows all WHO records matching a regular expression in a friendly yet
#   complete format. Works on the active channel only.
#
#   This enhanced version includes:
#   - Input validation and error handling
#   - Timeout protection for WHO requests
#   - Configurable case sensitivity and search fields
#   - Debug mode and statistics tracking
#   - Improved parsing and state management
#
# SETTINGS:
#   cgrep_case_sensitive - Enable case sensitive matching (default: off)
#   cgrep_debug         - Enable debug output (default: off)
#   cgrep_timeout       - Request timeout in seconds (default: 30)
#   cgrep_search_fields - Fields to search: nick, host, realname, all (default: all)
#
# FORMAT SETTINGS:
#   cgrep_match         - Matching record format
#   cgrep_line          - Start and end line format
#   cgrep_error         - Error message format
#   cgrep_debug         - Debug message format
#
################################################################################

use strict;
use warnings;
use Irssi;
use vars qw($VERSION %IRSSI);

$VERSION = "2.0.0";
%IRSSI = (
    authors     => "Pieter-Bas IJdens (Enhanced)",
    contact     => "irssi-scripts\@nospam.mi4.org.uk",
    name        => "cgrep",
    description => "Enhanced channel user search with regex - lists users matching specified patterns",
    license     => "GPLv2 or later",
    url         => "http://pieter-bas.ijdens.com/irssi/",
    changed     => "2024-01-01"
);

################################################################################
# STATE MANAGEMENT
################################################################################

# Encapsulated state to avoid global variable conflicts
my %cgrep_state = (
    busy         => 0,
    regexp       => "",
    compiled_regex => undef,
    results      => 0,
    timeout_tag  => undef,
    start_time   => 0,
);

# Statistics tracking
my %cgrep_stats = (
    total_searches    => 0,
    total_matches     => 0,
    avg_response_time => 0,
    last_search_time  => 0,
);

# Pre-compiled regex patterns for performance
my $hop_regex = qr/^(\d+)\s+/;
my $data_split_regex = qr/^(.*?):(.*?)$/;

################################################################################
# UTILITY FUNCTIONS
################################################################################

sub reset_state {
    # Reset the cgrep state to initial values
    if ($cgrep_state{timeout_tag}) {
        Irssi::timeout_remove($cgrep_state{timeout_tag});
    }

    %cgrep_state = (
        busy         => 0,
        regexp       => "",
        compiled_regex => undef,
        results      => 0,
        timeout_tag  => undef,
        start_time   => 0,
    );
}

sub debug_print {
    # Print debug message if debug mode is enabled
    my ($message) = @_;
    return unless Irssi::settings_get_bool("cgrep_debug");

    Irssi::printformat(MSGLEVEL_CLIENTCRAP, 'cgrep_debug', $message);
}

sub error_print {
    # Print formatted error message
    my ($msg) = @_;
    Irssi::printformat(MSGLEVEL_CLIENTCRAP, 'cgrep_error', $msg);
}

sub validate_regex {
    # Validate and compile a regular expression
    my ($pattern) = @_;

    return (0, "Empty pattern") unless defined $pattern && length($pattern);

    my $case_sensitive = Irssi::settings_get_bool("cgrep_case_sensitive");
    my $flags = $case_sensitive ? "" : "i";

    my $compiled;
    eval { $compiled = qr/(?$flags:$pattern)/ };
    if ($@) {
        my $error = $@;
        $error =~ s/ at .*? line \d+.*//;  # Clean up error message
        return (0, "Invalid regular expression: $error");
    }

    return (1, $compiled);
}

sub should_search_field {
    # Determine if a field should be included in search based on settings
    my ($field) = @_;
    my $search_fields = Irssi::settings_get_str("cgrep_search_fields");

    return 1 if $search_fields eq "all";
    return index($search_fields, $field) != -1;
}

################################################################################
# WHO COMMAND HANDLING
################################################################################

sub run_who {
    # Execute WHO command with timeout protection
    my ($server, $channel) = @_;

    debug_print("Executing WHO command for channel: $channel");

    # Set timeout to prevent hanging
    my $timeout = Irssi::settings_get_int("cgrep_timeout");
    $cgrep_state{timeout_tag} = Irssi::timeout_add_once($timeout * 1000, sub {
        if ($cgrep_state{busy}) {
            error_print("WHO request timed out after $timeout seconds");
            reset_state();
        }
    }, undef);

    # Set up event redirection
    $server->redirect_event(
        "who",
        1,
        $channel,
        0,
        "redir who_default",
        {
            "event 352" => "redir cgrep_evt_who_result",
            "event 315" => "redir cgrep_evt_who_end",
            ""          => "event empty"
        }
    );

    $cgrep_state{start_time} = time();
    $server->send_raw("WHO $channel");
}

################################################################################
# EVENT HANDLERS
################################################################################

sub event_who_result {
    # Handle individual WHO result entries
    my ($server, $data) = @_;

    return unless $cgrep_state{busy};

    debug_print("Processing WHO result: $data");

    # Parse the WHO response more robustly
    my ($start, $realname) = $data =~ /$data_split_regex/;
    unless (defined $start && defined $realname) {
        debug_print("WHO response parsing failed: $data");
        return;
    }

    # Split the first part into fields with limit for performance
    my @fields = split /\s+/, $start, 7;
    if (@fields < 7) {
        debug_print("Insufficient WHO fields in: $start");
        return;
    }

    my ($me, $channel, $ident, $host, $server_name, $nick, $mode) = @fields;

    # Extract hop count more reliably
    my $hops = "unknown";
    if ($realname =~ s/$hop_regex//) {
        $hops = $1;
    }

    # Build search string based on configured fields
    my @search_parts;
    push @search_parts, $nick if should_search_field("nick");
    push @search_parts, "$ident\@$host" if should_search_field("host");
    push @search_parts, $realname if should_search_field("realname");

    # If "all" is specified, include everything
    if (should_search_field("all")) {
        @search_parts = ($nick, "$ident\@$host", $realname, $channel, $server_name, $hops);
    }

    my $search_string = join(" ", @search_parts);

    # Apply the compiled regex
    if ($search_string =~ /$cgrep_state{compiled_regex}/) {
        Irssi::printformat(
            MSGLEVEL_CLIENTCRAP,
            'cgrep_match',
            $nick,
            "$ident\@$host",
            $realname,
            $channel,
            $server_name,
            $hops
        );

        $cgrep_state{results}++;
        debug_print("Match found: $nick");
    }
}

sub event_who_end {
    # Handle end of WHO results
    my ($server, $data) = @_;

    return unless $cgrep_state{busy};

    # Calculate response time
    my $response_time = time() - $cgrep_state{start_time};

    # Update statistics
    $cgrep_stats{total_searches}++;
    $cgrep_stats{total_matches} += $cgrep_state{results};
    $cgrep_stats{last_search_time} = $response_time;

    # Calculate running average response time
    if ($cgrep_stats{total_searches} == 1) {
        $cgrep_stats{avg_response_time} = $response_time;
    } else {
        $cgrep_stats{avg_response_time} =
            ($cgrep_stats{avg_response_time} * ($cgrep_stats{total_searches} - 1) + $response_time) /
            $cgrep_stats{total_searches};
    }

    # Display results summary
    my $results_msg = "End of list. Found $cgrep_state{results} matches in ${response_time}s";
    Irssi::printformat(MSGLEVEL_CLIENTCRAP, 'cgrep_line', $results_msg);

    debug_print("Search completed: $cgrep_state{results} matches, ${response_time}s response time");

    reset_state();
}

################################################################################
# COMMAND HANDLERS
################################################################################

sub cmd_cgrep {
    # Main cgrep command handler
    my ($data, $server, $window) = @_;

    # Trim whitespace
    $data =~ s/^\s+|\s+$//g;

    # Input validation
    if (!$data) {
        error_print("Usage: /cgrep <regexp>");
        error_print("Type /cgrep_help for more information");
        return;
    }

    # Server validation
    if (!$server) {
        error_print("Not connected to a server in this window");
        return;
    }

    # Window type validation
    if ($window->{type} ne "CHANNEL") {
        error_print("Not a channel window");
        return;
    }

    # Check if already busy
    if ($cgrep_state{busy}) {
        error_print("A search request is already in progress");
        error_print("Please wait for it to complete or reload the script");
        return;
    }

    # Validate and compile regex
    my ($valid, $compiled_or_error) = validate_regex($data);
    if (!$valid) {
        error_print($compiled_or_error);
        return;
    }

    # Set up search state
    $cgrep_state{busy} = 1;
    $cgrep_state{regexp} = $data;
    $cgrep_state{compiled_regex} = $compiled_or_error;
    $cgrep_state{results} = 0;

    # Display search start message
    my $case_info = Irssi::settings_get_bool("cgrep_case_sensitive") ? " (case sensitive)" : " (case insensitive)";
    my $fields_info = Irssi::settings_get_str("cgrep_search_fields");
    my $search_msg = "WHO on " . $window->{name} .
                    " filtered on '$data'$case_info, fields: $fields_info";

    Irssi::printformat(MSGLEVEL_CLIENTCRAP, 'cgrep_line', $search_msg);

    debug_print("Starting search with pattern: $data");

    # Execute the WHO command
    run_who($server, $window->{name});
}

sub cmd_cgrep_help {
    # Display help information
    Irssi::print("%Y═══════════════════════════════════════════════════════════════%n");
    Irssi::print("%Ycgrep v$VERSION - Enhanced Channel User Search%n");
    Irssi::print("%Y═══════════════════════════════════════════════════════════════%n");
    Irssi::print("");
    Irssi::print("%WCOMMANDS:%n");
    Irssi::print("  %G/cgrep <pattern>%n    - Search for users matching regex pattern");
    Irssi::print("  %G/cgrep_help%n         - Show this help information");
    Irssi::print("  %G/cgrep_stats%n        - Show search statistics");
    Irssi::print("");
    Irssi::print("%WSETTINGS:%n");
    Irssi::print("  %Gcgrep_case_sensitive%n - Enable case sensitive matching (default: OFF)");
    Irssi::print("  %Gcgrep_debug%n         - Enable debug output (default: OFF)");
    Irssi::print("  %Gcgrep_timeout%n       - Request timeout in seconds (default: 30)");
    Irssi::print("  %Gcgrep_search_fields%n - Fields to search (default: all)");
    Irssi::print("                          Options: nick, host, realname, all");
    Irssi::print("");
    Irssi::print("%WEXAMPLES:%n");
    Irssi::print("  %G/cgrep john%n         - Find users with 'john' anywhere");
    Irssi::print("  %G/cgrep ^admin%n       - Find users starting with 'admin'");
    Irssi::print("  %G/cgrep \\.org\$%n       - Find users with .org hostnames");
    Irssi::print("");
    Irssi::print("%WFORMAT THEMES:%n");
    Irssi::print("  Customize appearance with: cgrep_match, cgrep_line, cgrep_error, cgrep_debug");
}

sub cmd_cgrep_stats {
    # Display search statistics
    Irssi::print("%Y═══════════════════════════════════════════════════════════════%n");
    Irssi::print("%Ycgrep Statistics%n");
    Irssi::print("%Y═══════════════════════════════════════════════════════════════%n");

    if ($cgrep_stats{total_searches} == 0) {
        Irssi::print("No searches performed yet.");
        return;
    }

    my $avg_matches = sprintf("%.1f", $cgrep_stats{total_matches} / $cgrep_stats{total_searches});
    my $avg_time = sprintf("%.2f", $cgrep_stats{avg_response_time});
    my $last_time = sprintf("%.2f", $cgrep_stats{last_search_time});

    Irssi::print("Total searches: %G$cgrep_stats{total_searches}%n");
    Irssi::print("Total matches: %G$cgrep_stats{total_matches}%n");
    Irssi::print("Average matches per search: %G$avg_matches%n");
    Irssi::print("Average response time: %G${avg_time}s%n");
    Irssi::print("Last search response time: %G${last_time}s%n");
}

################################################################################
# INITIALIZATION
################################################################################

# Register settings with defaults
Irssi::settings_add_bool("cgrep", "cgrep_case_sensitive", 0);
Irssi::settings_add_bool("cgrep", "cgrep_debug", 0);
Irssi::settings_add_int("cgrep", "cgrep_timeout", 30);
Irssi::settings_add_str("cgrep", "cgrep_search_fields", "all");

# Register theme formats
Irssi::theme_register([
    'cgrep_match',
    '%GWHO:%n {channick_hilight $0} [{hilight $1}] is "{hilight $2}"%n on {channel $3} [server: {hilight $4}, hops: {hilight $5}]',

    'cgrep_line',
    '%R══════════════%n {hilight $0} %R══════════════%n',

    'cgrep_error',
    '%R[cgrep ERROR]%n $0',

    'cgrep_debug',
    '%B[cgrep DEBUG]%n $0'
]);

# Register signal handlers
Irssi::signal_add({
    'redir cgrep_evt_who_result' => \&event_who_result,
    'redir cgrep_evt_who_end'    => \&event_who_end
});

# Register commands
Irssi::command_bind("cgrep", \&cmd_cgrep);
Irssi::command_bind("cgrep_help", \&cmd_cgrep_help);
Irssi::command_bind("cgrep_stats", \&cmd_cgrep_stats);

# Cleanup on script unload
sub UNLOAD {
    reset_state();
}

################################################################################

Irssi::print("cgrep v$VERSION loaded. Type /cgrep_help for usage information.");

################################################################################
