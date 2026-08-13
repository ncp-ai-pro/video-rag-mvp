import pytest

from app.video_identity import extract_youtube_urls, youtube_video_identity


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://www.youtube.com/watch?v=eOqXQqg0_Dw", "eOqXQqg0_Dw"),
        ("https://youtu.be/eOqXQqg0_Dw?feature=share", "eOqXQqg0_Dw"),
        ("https://m.youtube.com/watch?v=eOqXQqg0_Dw", "eOqXQqg0_Dw"),
        ("https://www.youtube.com/shorts/eOqXQqg0_Dw", "eOqXQqg0_Dw"),
        ("https://www.youtube.com/embed/eOqXQqg0_Dw", "eOqXQqg0_Dw"),
        ("https://www.youtube.com/live/eOqXQqg0_Dw", "eOqXQqg0_Dw"),
    ],
)
def test_youtube_video_identity_normalizes_supported_url_shapes(url, video_id):
    identity = youtube_video_identity(url)

    assert identity is not None
    assert identity.provider == "youtube"
    assert identity.provider_video_id == video_id
    assert identity.canonical_url == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.parametrize(
    ("url", "seconds"),
    [
        ("https://youtu.be/abc123?t=1h2m3s", 3723),
        ("https://www.youtube.com/watch?v=abc123&start=90", 90),
        ("https://www.youtube.com/embed/abc123?time_continue=45s", 45),
        ("https://www.youtube.com/watch?v=abc123#t=12", 12),
    ],
)
def test_youtube_video_identity_keeps_start_hint(url, seconds):
    assert youtube_video_identity(url).start_seconds_hint == seconds


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/@creator",
        "https://www.youtube.com/watch?v=not/a-video",
        "https://example.com/watch?v=abc123",
        "https://youtu.be/",
    ],
)
def test_youtube_video_identity_rejects_non_video_urls(url):
    assert youtube_video_identity(url) is None


def test_extract_youtube_urls_deduplicates_by_video_id_and_preserves_first_order():
    text = (
        "첫 영상 https://youtu.be/first123?t=5, "
        "중복 https://www.youtube.com/watch?v=first123&start=99 그리고 "
        "둘째 https://m.youtube.com/shorts/second_456."
    )

    identities = extract_youtube_urls(text)

    assert [item.provider_video_id for item in identities] == ["first123", "second_456"]
    assert identities[0].start_seconds_hint == 5
    assert identities[1].canonical_url == "https://www.youtube.com/watch?v=second_456"
