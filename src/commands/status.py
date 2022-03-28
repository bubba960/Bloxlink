from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import GOLD_COLOR # pylint: disable=import-error, no-name-in-module
from discord import Embed


get_features, has_premium = Bloxlink.get_module("premium", attrs=["get_features", "has_premium"])


@Bloxlink.command
class StatusCommand(Bloxlink.Module):
    """view your Bloxlink premium status"""

    def __init__(self):
        self.examples = ["@justin"]
        self.arguments = [{
            "prompt": "Please specify the user to view the status of.",
            "name": "user",
            "type": "user",
            "optional": True
        }]
        self.category = "Premium"
        self.free_to_use = True
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_only = True


    @Bloxlink.subcommand()
    async def user(self, CommandArgs):
        """view a user's premium status"""

        profile = await has_premium(user=CommandArgs.author)

        embed = Embed()
        embed.set_author(name=str(CommandArgs.author), icon_url=CommandArgs.author.avatar.url)

        if "premium" in profile.features:
            embed.add_field(name="Premium Status", value="Active")
            embed.colour = GOLD_COLOR
        else:
            embed.description = f"This user does not have premium. They may purchase it [here](https://blox.link)."

        # if profile.features:
        #     embed.add_field(name="Features", value=", ".join(profile.features.keys()))

        if profile.user_facing_tier:
            embed.add_field(name="Tier", value=profile.user_facing_tier)

        if profile.type:
            embed.add_field(name="Charge Source", value=profile.type)

        await CommandArgs.response.send(embed=embed)


    @Bloxlink.subcommand()
    async def server(self, CommandArgs):
        """get the server's premium status"""

        profile = await has_premium(guild=CommandArgs.guild)

        embed = Embed()
        embed.set_author(name=CommandArgs.guild.name, icon_url=CommandArgs.guild.icon.url)

        if "premium" in profile.features:
            embed.add_field(name="Premium Status", value="Active")
            embed.colour = GOLD_COLOR
        else:
            embed.description = f"This server does not have premium. They may purchase it [here](https://blox.link)."

        # if profile.features:
        #     embed.add_field(name="Features", value=", ".join(profile.features.keys()))

        if profile.user_facing_tier:
            embed.add_field(name="Tier", value=profile.user_facing_tier)

        if profile.type:
            embed.add_field(name="Charge Source", value=profile.type)

        await CommandArgs.response.send(embed=embed)
