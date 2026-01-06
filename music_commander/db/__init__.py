"""Database layer for Mixxx integration."""

from music_commander.db.models import (
    Base,
    Crate,
    CrateTrack,
    Cue,
    Playlist,
    PlaylistTrack,
    Track,
    TrackLocation,
)
from music_commander.db.queries import (
    add_track_to_crate,
    add_track_to_playlist,
    create_crate,
    create_playlist,
    get_crate_tracks,
    get_playlist_tracks,
    get_track_by_id,
    get_track_by_location,
    list_crates,
    list_playlists,
    query_tracks,
    remove_track_from_crate,
    remove_track_from_playlist,
    update_track,
)
from music_commander.db.session import get_session

__all__ = [
    # Models
    "Base",
    "Track",
    "TrackLocation",
    "Playlist",
    "PlaylistTrack",
    "Crate",
    "CrateTrack",
    "Cue",
    # Session
    "get_session",
    # Read queries
    "query_tracks",
    "get_track_by_id",
    "get_track_by_location",
    "list_playlists",
    "get_playlist_tracks",
    "list_crates",
    "get_crate_tracks",
    # Write operations
    "update_track",
    "create_playlist",
    "add_track_to_playlist",
    "remove_track_from_playlist",
    "create_crate",
    "add_track_to_crate",
    "remove_track_from_crate",
]
