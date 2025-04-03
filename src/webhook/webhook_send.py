from discord_webhook import DiscordWebhook, DiscordEmbed
from datetime import datetime
from enum import IntEnum
import time


class DiscordWebhookLogger:
    class WebhookLogStatus(IntEnum):
        SUCCESS = 0xB0D89B
        FAIL = 0xDF8C97
        WORKING = 0x7967C3

    def __init__(self, url, title, desc):
        self.webhook = DiscordWebhook(url, rate_limit_retry=True)
        self.embed = DiscordEmbed(
            title, desc, color=DiscordWebhookLogger.WebhookLogStatus.WORKING
        )
        self.embed.add_embed_field(
            name="Time", value=str(datetime.fromtimestamp(time.time())), inline=False
        )
        self.embed.set_footer("...from builder")
        self.webhook.add_embed(self.embed)
        self.webhook.execute()

        self.webhook.edit()

    def add_field(self, fname: str):
        self.embed.add_embed_field(name=fname, value="", inline=False)
        self.webhook.edit()

    def add_message_to_last_field(self, msg: str):
        self.embed.get_embed_fields()[0]["value"] = str(
            datetime.fromtimestamp(time.time())
        )
        self.embed.get_embed_fields()[-1]["value"] += "\n" + msg
        self.webhook.edit()

    def change_status(self, status: WebhookLogStatus):
        self.embed.set_color(status)
        match status:
            case DiscordWebhookLogger.WebhookLogStatus.SUCCESS:
                self.embed.set_title(":white_check_mark: Build Success")
                self.webhook.edit()
            case DiscordWebhookLogger.WebhookLogStatus.WORKING:
                self.embed.set_title(":person_running: Working...")
                self.webhook.edit()
            case DiscordWebhookLogger.WebhookLogStatus.FAIL:
                self.embed.set_title(":x: Build Fail!")
                self.webhook.edit()
