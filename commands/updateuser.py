from discord import Embed

from resources.module import get_module
give_roblox_stuff, get_user = get_module("roblox", attrs=["give_roblox_stuff", "get_user"])
post_event = get_module("utils", attrs=["post_event"])




async def setup(**kwargs):
	command = kwargs.get("command")
	client = kwargs.get("client")

	@command(name="updateuser", category="Administration", permissions={
		"raw": "manage_roles", "exceptions": {"roles": ["Bloxlink Updater"]} },
    aliases=["updateroles", "updaterole", "updatemember", "updatenickname", "updatenick", "update"], arguments=[
        {
            "prompt": "Please specify a user to update.",
            "type": "user",
            "name": "user"
        }
    ])
	async def updateuser(message, response, args, prefix):
		"""updates roles/nickname for the member"""

		author = args.parsed_args["user"]

		primary_account, _ = await get_user(author=author)

		if primary_account:

			added, removed, errored = await give_roblox_stuff(author, roblox_user=primary_account, complete=True)

			embed = Embed(title="Bloxlink Roles")

			if added:
				embed.add_field(name="Added", value="\n".join(added))
			if removed:
				embed.add_field(name="Removed", value="\n".join(removed))
			if errored:
				embed.add_field(name="Errored", value=errored[0])

			if not added and not removed and not errored:
				await response.success("All caught up! There are no roles to add/remove.")
				return

			embed.set_author(name=author, icon_url=author.avatar_url)

			await response.send(embed=embed)

		else:
			await response.error(f"**{author}** is not linked to Bloxlink.")
