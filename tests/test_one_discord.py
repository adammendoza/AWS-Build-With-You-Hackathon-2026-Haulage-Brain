from load_quoting_swarm.one_discord import OneDiscordPublisher


def test_one_discovers_current_action_without_hardcoded_id(monkeypatch) -> None:
    monkeypatch.setenv("ONE_DISCORD_CONNECTION_KEY", "discord-connection")
    monkeypatch.setenv("ONE_DISCORD_CHANNEL_ID", "channel-123")
    monkeypatch.setattr("load_quoting_swarm.one_discord.shutil.which", lambda _: "one")
    publisher = OneDiscordPublisher()
    calls = []

    def fake_run(args):
        calls.append(args)
        return {
            "result": {
                "actionId": "discord.messages.create",
                "method": "POST",
                "path": "/channels/{channelId}/messages",
            }
        }

    monkeypatch.setattr(publisher, "_run", fake_run)

    assert publisher._resolve_send_action() == "discord.messages.create"
    assert calls[0][:4] == [
        "actions",
        "find",
        "discord",
        "send a message to a channel",
    ]
    assert "--ai-model" not in calls[0]
