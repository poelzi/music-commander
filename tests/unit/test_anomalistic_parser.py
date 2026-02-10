"""Unit tests for Anomalistic portal HTML content parser."""

from __future__ import annotations

import pytest

from music_commander.anomalistic.parser import (
    ParsedRelease,
    TrackInfo,
    extract_cover_art,
    extract_credits,
    extract_download_urls,
    extract_label,
    extract_tracklist,
    parse_release_content,
    parse_title,
)

# ---------------------------------------------------------------------------
# Title parsing tests
# ---------------------------------------------------------------------------


class TestParseTitle:
    """Tests for parse_title()."""

    def test_standard_em_dash(self):
        artist, album = parse_title("XianZai \u2013 Irrational Conjunction")
        assert artist == "XianZai"
        assert album == "Irrational Conjunction"

    def test_html_entity_en_dash(self):
        # WordPress often encodes em-dash as &#8211;
        artist, album = parse_title("XianZai &#8211; Irrational Conjunction")
        assert artist == "XianZai"
        assert album == "Irrational Conjunction"

    def test_va_prefix_dash(self):
        artist, album = parse_title("VA \u2013 Cyber Alchemist")
        assert artist == "Various Artists"
        assert album == "Cyber Alchemist"

    def test_va_prefix_space(self):
        artist, album = parse_title("V/A Kreepsy Origins")
        assert artist == "Various Artists"
        assert album == "Kreepsy Origins"

    def test_va_prefix_hyphen(self):
        artist, album = parse_title("VA - Skridmarks Vol.2")
        assert artist == "Various Artists"
        assert album == "Skridmarks Vol.2"

    def test_standard_hyphen_space(self):
        artist, album = parse_title("BRKHO - WHY DO WE PICK FIGHTS WITH GAIA")
        assert artist == "BRKHO"
        assert album == "WHY DO WE PICK FIGHTS WITH GAIA"

    def test_no_delimiter(self):
        artist, album = parse_title("Just An Album Title")
        assert artist == "Various Artists"
        assert album == "Just An Album Title"

    def test_strip_label_suffix(self):
        artist, album = parse_title("Voidscream \u2013 Jund (Anomalistic Records)")
        assert artist == "Voidscream"
        assert album == "Jund"

    def test_strip_label_suffix_audio(self):
        artist, album = parse_title("Artist \u2013 Album (Some Audio)")
        assert artist == "Artist"
        assert album == "Album"

    def test_preserve_non_label_parentheses(self):
        artist, album = parse_title("VA \u2013 Cyber Alchemist (Anomalistic and Xibalba)")
        # "Anomalistic and Xibalba" doesn't match the label pattern
        assert artist == "Various Artists"
        assert album == "Cyber Alchemist (Anomalistic and Xibalba)"

    def test_html_amp_entity(self):
        artist, album = parse_title("VA &#8211; Beyond of Knight &amp; Devil")
        assert artist == "Various Artists"
        assert album == "Beyond of Knight & Devil"

    def test_multiple_dashes_splits_on_first(self):
        artist, album = parse_title("Rose Red Flechette \u2013 The Destruction Myth")
        assert artist == "Rose Red Flechette"
        assert album == "The Destruction Myth"

    def test_empty_title(self):
        artist, album = parse_title("")
        assert artist == "Various Artists"
        assert album == ""

    def test_whitespace_title(self):
        artist, album = parse_title("   ")
        assert artist == "Various Artists"
        assert album == ""


# ---------------------------------------------------------------------------
# Download URL extraction tests
# ---------------------------------------------------------------------------

# Real HTML from XianZai post
_XIANZAI_HTML = """
<p><a href="https://www.anomalisticrecords.com/xianzai/XianZai%20-%20Irrational%20Conjunction%20-%20WAV.zip">DOWNLOAD – WAV</a></p>
<p><a href="https://www.anomalisticrecords.com/xianzai/XianZai%20-%20Irrational%20Conjunction%20-%20MP3.zip">DOWNLOAD – MP3</a></p>
"""

# HTML with image-based download buttons (older posts)
_IMAGE_BUTTON_HTML = """
<p><a href="http://anomalisticrecords.com/voidscream/jund/Voidscream - Jund (WAV).zip"><img src="wav-download.png" /></a>
   <a href="http://anomalisticrecords.com/voidscream/jund/Voidscream%20-%20Jund%20%28MP3%29.zip"><img src="mp3-download.png" /></a></p>
"""

# HTML with http:// URLs (some older posts)
_HTTP_HTML = """
<p><a href="http://www.anomalisticrecords.com/Cosmogonia/Cosmogon%C3%ADa%20-%20Flower%20Day%20-%20WAV.zip">DOWNLOAD – WAV</a></p>
<p><a href="http://www.anomalisticrecords.com/Cosmogonia/Cosmogonia%20-%20Flower%20Day%20-%20MP3.zip">DOWNLOAD – MP3</a></p>
"""


class TestExtractDownloadUrls:
    """Tests for extract_download_urls()."""

    def test_standard_wav_mp3(self):
        urls = extract_download_urls(_XIANZAI_HTML)
        assert "wav" in urls
        assert "mp3" in urls
        assert "WAV.zip" in urls["wav"]
        assert "MP3.zip" in urls["mp3"]

    def test_image_button_downloads(self):
        urls = extract_download_urls(_IMAGE_BUTTON_HTML)
        assert "wav" in urls
        assert "mp3" in urls

    def test_http_urls(self):
        urls = extract_download_urls(_HTTP_HTML)
        assert "wav" in urls
        assert "mp3" in urls

    def test_no_download_links(self):
        html = "<p>Just some text without any download links.</p>"
        urls = extract_download_urls(html)
        assert urls == {}

    def test_ignores_non_anomalistic_links(self):
        html = """
        <p><a href="https://soundcloud.com/someone/track">Listen</a></p>
        <p><a href="https://www.anomalisticrecords.com/test/WAV.zip">WAV</a></p>
        """
        urls = extract_download_urls(html)
        assert "wav" in urls
        assert len(urls) == 1

    def test_unclassified_archive(self):
        html = '<p><a href="https://www.anomalisticrecords.com/test/archive.rar">DOWNLOAD</a></p>'
        urls = extract_download_urls(html)
        assert "download" in urls
        assert urls["download"].endswith(".rar")

    def test_rar_with_format_hint(self):
        html = '<p><a href="https://www.anomalisticrecords.com/test/Album-WAV.rar">WAV</a></p>'
        urls = extract_download_urls(html)
        assert "wav" in urls


# ---------------------------------------------------------------------------
# Cover art extraction tests
# ---------------------------------------------------------------------------


class TestExtractCoverArt:
    """Tests for extract_cover_art()."""

    def test_first_img_with_srcset(self):
        html = """
        <figure class="wp-block-image size-large">
            <img src="https://example.com/cover-1024x1024.jpg"
                 srcset="https://example.com/cover-300x300.jpg 300w,
                         https://example.com/cover-1024x1024.jpg 1024w,
                         https://example.com/cover-2048x2048.jpg 2048w" />
        </figure>
        """
        url = extract_cover_art(html)
        assert url == "https://example.com/cover-2048x2048.jpg"

    def test_first_img_no_srcset(self):
        html = '<img src="https://example.com/cover.jpg" />'
        url = extract_cover_art(html)
        assert url == "https://example.com/cover.jpg"

    def test_no_images(self):
        html = "<p>No images here.</p>"
        url = extract_cover_art(html)
        assert url is None

    def test_featured_media_fallback(self):
        html = "<p>No images here.</p>"
        post = {
            "_embedded": {"wp:featuredmedia": [{"source_url": "https://example.com/featured.jpg"}]}
        }
        url = extract_cover_art(html, post)
        assert url == "https://example.com/featured.jpg"

    def test_prefers_content_over_featured(self):
        html = '<img src="https://example.com/content.jpg" />'
        post = {
            "_embedded": {"wp:featuredmedia": [{"source_url": "https://example.com/featured.jpg"}]}
        }
        url = extract_cover_art(html, post)
        assert url == "https://example.com/content.jpg"


# ---------------------------------------------------------------------------
# Tracklist extraction tests
# ---------------------------------------------------------------------------

_VA_TRACKLIST_HTML = """
<p>1.- Tuvstarr Princess and the Troll King – Vutt'un [174 bpms]<br>
2.- Vow of Silence – Depuratus [170 bpms]<br>
3.- Azeem O Shaan Shahenshah – Tormento [156 bpms]</p>
"""

_NUMBERED_TRACKLIST_HTML = """
<p>1- Rebirth = [Infinite Bucle] [77bpms]<br>
2- Six Realms of Reincarnations [225 bpms]<br>
3- Hyperdimensional Manipulation of Reality – Deadhead &amp; Neormm [200 bpms]</p>
"""

_OL_TRACKLIST_HTML = """
<ol>
<li>Cosmogonía – Twilight</li>
<li>Cosmogonía – Flower Day</li>
</ol>
"""

_DASH_NUMBERED_TRACKLIST = """
<p>01 – Erf – His Royal Highness<br>
02 – Sepehraka – Inner Emotions<br>
03 – Yaminahua – Overture</p>
"""


class TestExtractTracklist:
    """Tests for extract_tracklist()."""

    def test_va_tracklist_with_bpm(self):
        tracks = extract_tracklist(_VA_TRACKLIST_HTML)
        assert len(tracks) == 3
        assert tracks[0].number == 1
        assert tracks[0].title == "Tuvstarr Princess and the Troll King"
        assert tracks[0].artist == "Vutt'un"
        assert tracks[0].bpm == "174"

    def test_numbered_tracklist(self):
        tracks = extract_tracklist(_NUMBERED_TRACKLIST_HTML)
        assert len(tracks) >= 2
        assert tracks[1].number == 2
        assert "Six Realms" in tracks[1].title
        assert tracks[1].bpm == "225"

    def test_collab_artist(self):
        tracks = extract_tracklist(_NUMBERED_TRACKLIST_HTML)
        assert len(tracks) >= 3
        assert tracks[2].artist is not None
        assert "Deadhead" in tracks[2].artist

    def test_dash_numbered_tracklist(self):
        tracks = extract_tracklist(_DASH_NUMBERED_TRACKLIST)
        assert len(tracks) == 3
        assert tracks[0].number == 1
        # "Erf – His Royal Highness" should split into title/artist
        assert tracks[0].artist is not None

    def test_no_tracklist(self):
        html = "<p>Just a description with no numbered tracks.</p>"
        tracks = extract_tracklist(html)
        assert tracks == []

    def test_bpm_range(self):
        html = "<p>1- Track Title [225 – 250 – 280 bpms]</p>"
        tracks = extract_tracklist(html)
        assert len(tracks) == 1
        assert tracks[0].bpm is not None
        assert "225" in tracks[0].bpm


# ---------------------------------------------------------------------------
# Credits extraction tests
# ---------------------------------------------------------------------------


class TestExtractCredits:
    """Tests for extract_credits()."""

    def test_standard_credits(self):
        html = """
        <p>Written and Produced by: XianZai<br>
        Mastering at: Optinervear Studio<br>
        Artwork by: XianZai (Carl Abdo)<br>
        Released by: Anomalistic Records</p>
        """
        credits = extract_credits(html)
        assert credits is not None
        assert "XianZai" in credits
        assert "Optinervear" in credits
        assert "Anomalistic" in credits

    def test_compiled_by(self):
        html = "<p>Compiled by Neormm<br>Master by Kri Samadhi</p>"
        credits = extract_credits(html)
        assert credits is not None
        assert "Neormm" in credits
        assert "Kri Samadhi" in credits

    def test_no_credits(self):
        html = "<p>Just a description with no credit patterns.</p>"
        credits = extract_credits(html)
        assert credits is None

    def test_mastered_by(self):
        html = "<p>Mastered by: Arcek</p>"
        credits = extract_credits(html)
        assert credits is not None
        assert "Arcek" in credits


# ---------------------------------------------------------------------------
# Integration: parse_release_content
# ---------------------------------------------------------------------------


_FULL_POST = {
    "id": 3322,
    "title": {"rendered": "XianZai &#8211; Irrational Conjunction"},
    "content": {
        "rendered": """
<figure class="wp-block-image size-large">
    <img src="https://darkpsyportal.anomalisticrecords.com/wp-content/uploads/2023/05/XianZai-Irrational-Conjunction-1024x1024.jpg"
         srcset="https://darkpsyportal.anomalisticrecords.com/wp-content/uploads/2023/05/XianZai-Irrational-Conjunction-1024x1024.jpg 1024w,
                 https://darkpsyportal.anomalisticrecords.com/wp-content/uploads/2023/05/XianZai-Irrational-Conjunction-2048x2048.jpg 2048w" />
</figure>
<p>Written and Produced by: XianZai<br>Mastering at: Optinervear Studio<br>Artwork by: XianZai (Carl Abdo)<br>Released by: Anomalistic Records</p>
<p><a href="https://www.anomalisticrecords.com/xianzai/XianZai%20-%20Irrational%20Conjunction%20-%20WAV.zip">DOWNLOAD – WAV</a></p>
<p><a href="https://www.anomalisticrecords.com/xianzai/XianZai%20-%20Irrational%20Conjunction%20-%20MP3.zip">DOWNLOAD – MP3</a></p>
"""
    },
    "date": "2023-05-09T15:27:09",
    "categories": [3],
}


class TestExtractLabel:
    """Tests for extract_label()."""

    def test_released_by_colon(self):
        html = "<p>Released by: Anomalistic Records</p>"
        assert extract_label(html) == "Anomalistic Records"

    def test_released_on(self):
        html = "<p>Released on Anomalistic Records</p>"
        assert extract_label(html) == "Anomalistic Records"

    def test_released_by_no_colon(self):
        html = "<p>Released by Anomalistic Records</p>"
        assert extract_label(html) == "Anomalistic Records"

    def test_multiple_labels_takes_first(self):
        html = "<p>Released on Anomalistic & Xibalba Records</p>"
        assert extract_label(html) == "Anomalistic"

    def test_multiple_labels_and(self):
        html = "<p>Released by Anomalistic and Xibalba Records</p>"
        assert extract_label(html) == "Anomalistic"

    def test_no_label(self):
        html = "<p>Just some content with no label info.</p>"
        assert extract_label(html) is None

    def test_trailing_punctuation_stripped(self):
        html = "<p>Released by: Anomalistic Records.</p>"
        assert extract_label(html) == "Anomalistic Records"

    def test_embedded_in_credits_block(self):
        html = (
            "<p>Written and Produced by: XianZai<br>"
            "Mastering at: Optinervear Studio<br>"
            "Released by: Anomalistic Records</p>"
        )
        assert extract_label(html) == "Anomalistic Records"


class TestParseReleaseContent:
    """Tests for parse_release_content()."""

    def test_full_post(self):
        result = parse_release_content(_FULL_POST)
        assert result.artist == "XianZai"
        assert result.album == "Irrational Conjunction"
        assert "wav" in result.download_urls
        assert "mp3" in result.download_urls
        assert result.cover_art_url is not None
        assert "2048x2048" in result.cover_art_url
        assert result.credits is not None
        assert "Optinervear" in result.credits
        assert result.release_date == "2023-05-09T15:27:09"
        assert result.label == "Anomalistic Records"

    def test_va_post(self):
        post = {
            "title": {"rendered": "VA &#8211; Cyber Alchemist (Anomalistic and Xibalba)"},
            "content": {
                "rendered": """
<p>1.- Track One – Artist1 [174 bpms]<br>2.- Track Two – Artist2 [170 bpms]</p>
<p><a href="https://www.anomalisticrecords.com/VA/VA%20-%20Cyber%20Alchemist%20WAV.zip">DOWNLOAD – WAV</a></p>
"""
            },
            "date": "2023-01-22T15:50:57",
        }
        result = parse_release_content(post)
        assert result.artist == "Various Artists"
        assert result.album == "Cyber Alchemist (Anomalistic and Xibalba)"
        assert len(result.tracklist) == 2
        assert result.tracklist[0].artist == "Artist1"

    def test_minimal_post(self):
        post = {
            "title": {"rendered": "Unknown"},
            "content": {"rendered": "<p>Minimal content.</p>"},
            "date": None,
        }
        result = parse_release_content(post)
        assert result.artist == "Various Artists"
        assert result.album == "Unknown"
        assert result.download_urls == {}
        assert result.tracklist == []
        assert result.credits is None
        assert result.cover_art_url is None
        assert result.label is None
