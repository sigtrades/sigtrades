from sigtrades_core.discord.message_text import extract_discord_message_text


def test_extract_embed_description_only():
    data = {
        "content": "",
        "embeds": [
            {
                "description": (
                    "BRUN 30 C 2026-07-17\n"
                    "$805K AVG$5.57 39DTE\n"
                    "Informational purposes only. Not financial advice."
                )
            }
        ],
    }
    text = extract_discord_message_text(data)
    assert "BRUN 30 C 2026-07-17" in text
    assert "$805K AVG$5.57 39DTE" in text


def test_extract_prefers_content_plus_embed():
    data = {
        "content": "prefix",
        "embeds": [{"description": "body"}],
    }
    assert extract_discord_message_text(data) == "prefix\nbody"
