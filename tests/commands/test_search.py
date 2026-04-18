"""Unit tests for search command functionality."""

from unittest.mock import Mock, patch

import pytest

from rekordbox_edit.commands.search import search_command


@pytest.fixture(autouse=True)
def mock_logger():
    with patch("rekordbox_edit.commands.search.logger") as mock_log:
        yield mock_log


class TestSearchCommand:
    """Base tests for search command behaviour."""

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_search_calls_print_track_info_by_default(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
        make_djmd_content_item,
    ):
        """Default output calls print_track_info with query results."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        content = make_djmd_content_item(ID="AAA111")
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [content]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(search_command, [])

        assert result.exit_code == 0
        mock_print_track_info.assert_called_once_with([content])

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_print_ids_outputs_space_separated_ids(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
        make_djmd_content_item,
    ):
        """--print ids outputs space-separated track IDs."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [
            make_djmd_content_item(ID="AAA111"),
            make_djmd_content_item(ID="BBB222"),
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(search_command, ["--print", "ids"])

        assert result.exit_code == 0
        assert "AAA111 BBB222" in result.output
        mock_print_track_info.assert_not_called()

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_print_silent_produces_no_output(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
        make_djmd_content_item,
    ):
        """--print silent produces no output."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [
            make_djmd_content_item(ID="AAA111")
        ]
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        result = CliRunner().invoke(search_command, ["--print", "silent"])

        assert result.exit_code == 0
        assert result.output.strip() == ""
        mock_print_track_info.assert_not_called()

    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_search_no_db_session_raises(self, mock_db_class):
        """RuntimeError is raised (and propagated) when the db has no session."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = None

        from click.testing import CliRunner

        result = CliRunner().invoke(search_command, [])

        assert result.exit_code != 0

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_filters_passed_to_get_filtered_content(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
    ):
        """Filter options are forwarded correctly to get_filtered_content."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        CliRunner().invoke(
            search_command,
            ["--artist", "Daft Punk", "--format", "flac", "--match-all"],
        )

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["artists"] == ("Daft Punk",)
        assert call_kwargs["formats"] == ("flac",)
        assert call_kwargs["match_all"] is True


class TestSearchStdinPiping:
    """Test search command reading track IDs from stdin when piped."""

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_reads_track_ids_from_stdin_when_piped(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
    ):
        """When stdin is piped with no args, those IDs are used as the filter."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(search_command, [], input="190993005 108916663 59476253")

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["track_id_args"] == ["190993005", "108916663", "59476253"]

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_merges_stdin_ids_with_argument_ids(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
    ):
        """When both TRACK_IDS args and piped stdin are provided, they are combined."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(
            search_command,
            ["190993005", "108916663"],
            input="59476253 113475696",
        )

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert call_kwargs["track_id_args"] == [
            "190993005",
            "108916663",
            "59476253",
            "113475696",
        ]

    @patch("rekordbox_edit.commands.search.print_track_info")
    @patch("rekordbox_edit.commands.search.get_filtered_content")
    @patch("rekordbox_edit.commands.search.Rekordbox6Database")
    def test_empty_stdin_does_not_affect_track_ids(
        self,
        mock_db_class,
        mock_get_filtered_content,
        mock_print_track_info,
    ):
        """Whitespace-only piped stdin is ignored."""
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_db.session = Mock()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_get_filtered_content.return_value = mock_result

        from click.testing import CliRunner

        runner = CliRunner()
        runner.invoke(search_command, [], input="   ")

        call_kwargs = mock_get_filtered_content.call_args.kwargs
        assert not call_kwargs["track_id_args"]
