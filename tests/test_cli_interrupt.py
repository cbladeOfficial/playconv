"""
Unit tests for graceful Ctrl+C (KeyboardInterrupt) and exit handling.
Verifies that interrupting execution outputs a pleasant exit message with zero emojis,
and suppresses Python default tracebacks and click.Abort outputs.
"""

import sys
from click.testing import CliRunner
import click
import pytest

import playconv.cli as cli_module
from playconv.cli import GracefulGroup
from playconv.ui import display_exit_message


@pytest.fixture(autouse=True)
def reset_exit_handled():
    cli_module._exit_handled = False
    yield
    cli_module._exit_handled = False


def test_display_exit_message_interrupted(capsys):
    """Test interrupted exit message format and zero emojis."""
    display_exit_message(interrupted=True)
    captured = capsys.readouterr()
    output = captured.out
    assert "INTERRUPTED" in output
    assert "Operation cancelled by user (Ctrl+C)." in output
    assert "Exiting cleanly." in output
    assert "Goodbye! Thanks for using PlayConv." in output
    assert "Traceback" not in output
    assert "KeyboardInterrupt" not in output


def test_display_exit_message_graceful(capsys):
    """Test manual exit message format."""
    display_exit_message(interrupted=False)
    captured = capsys.readouterr()
    output = captured.out
    assert "EXIT" in output
    assert "PlayConv closed gracefully." in output
    assert "Have a wonderful day with your music." in output


def test_graceful_group_catches_keyboard_interrupt():
    """Verify that a Click command raising KeyboardInterrupt exits cleanly with pleasant message."""
    @click.group(cls=GracefulGroup)
    def test_group():
        pass

    @test_group.command("fail")
    def fail_cmd():
        raise KeyboardInterrupt()

    runner = CliRunner()
    result = runner.invoke(test_group, ["fail"])
    assert result.exit_code == 0
    assert "INTERRUPTED" in result.output
    assert "Operation cancelled by user (Ctrl+C)." in result.output
    assert "Traceback" not in result.output
    assert "Aborted!" not in result.output


def test_graceful_group_catches_abort():
    """Verify that a Click command raising click.Abort exits cleanly with pleasant message."""
    @click.group(cls=GracefulGroup)
    def test_group():
        pass

    @test_group.command("abort")
    def abort_cmd():
        raise click.Abort()

    runner = CliRunner()
    result = runner.invoke(test_group, ["abort"])
    assert result.exit_code == 0
    assert "INTERRUPTED" in result.output
    assert "Aborted!" not in result.output
