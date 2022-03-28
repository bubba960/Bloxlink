import re
import traceback
import asyncio
#import sentry_sdk
from concurrent.futures._base import CancelledError
import discord
from ..exceptions import PermissionError, CancelledPrompt, Message, CancelCommand, RobloxAPIError, RobloxDown, Error # pylint: disable=redefined-builtin, import-error
from ..structures import Bloxlink, Args, Command, Locale, Arguments, Response, Application # pylint: disable=import-error, no-name-in-module
from ..constants import MAGIC_ROLES, DEFAULTS, RELEASE, CLUSTER_ID, ORANGE_COLOR # pylint: disable=import-error, no-name-in-module
from ..secrets import TOKEN # pylint: disable=import-error, no-name-in-module
from config import BOTS # pylint: disable=import-error, no-name-in-module, no-name-in-module


fetch = Bloxlink.get_module("utils", attrs=["fetch"])
get_enabled_addons = Bloxlink.get_module("addonsm", attrs="get_enabled_addons")
get_guild_value, set_db_value = Bloxlink.get_module("cache", attrs=["get_guild_value", "set_db_value"])
get_restriction = Bloxlink.get_module("blacklist", attrs=["get_restriction"])
has_magic_role = Bloxlink.get_module("extras", attrs=["has_magic_role"])
has_premium = Bloxlink.get_module("premium", attrs=["has_premium"])


BOT_ID = BOTS[RELEASE]
COMMANDS_URL = f"https://discord.com/api/v8/applications/{BOT_ID}/commands" if RELEASE != "LOCAL" else f"https://discord.com/api/v8/applications/{BOT_ID}/guilds/439265180988211211/commands"
GUILD_COMMANDS_URL = "https://discord.com/api/v8/applications/{BOT_ID}/guilds/{GUILD_ID}/commands"

@Bloxlink.module
class Commands(Bloxlink.Module):
    """mannages interaction commands"""
    def __init__(self):
        self.commands   = {}

    async def __loaded__(self):
        """sync the slash commands and context-menus"""

        if CLUSTER_ID == 0:
            return

            interaction_commands = []
            all_guild_commands = {}

            for command in self.commands.values():
                if isinstance(command, Command):
                    command_json = self.slash_command_to_json(command)
                else:
                    command_json = self.app_command_to_json(command)

                if command.slash_enabled:
                    if command.slash_guilds and RELEASE == "LOCAL":
                        interaction_commands.append(command_json)
                    elif not command.slash_guilds:
                        interaction_commands.append(command_json)

                if command.slash_guilds:
                    for guild_id in command.slash_guilds:
                        all_guild_commands[guild_id] = all_guild_commands.get(guild_id) or []
                        all_guild_commands[guild_id].append(command_json)


            for guild_command_id, guild_commands in all_guild_commands.items():
                text2, response2 = await fetch(GUILD_COMMANDS_URL.format(BOT_ID=BOT_ID, GUILD_ID=guild_command_id), "PUT", body=guild_commands, headers={"Authorization": f"Bot {TOKEN}"}, raise_on_failure=False)

                if response2.status == 200:
                    Bloxlink.log(f"Successfully synced Slash Commands for guild {guild_command_id}")
                else:
                    print(interaction_commands, flush=True)
                    print(response2.status, text2, flush=True)

            text1, response1 = await fetch(COMMANDS_URL, "PUT", body=interaction_commands, headers={"Authorization": f"Bot {TOKEN}"}, raise_on_failure=False)

            if response1.status == 200:
                Bloxlink.log("Successfully synced the Global Slash Commands")
            else:
                print(interaction_commands, flush=True)
                print(response1.status, text1, flush=True)

    async def command_checks(self, command, response, author, channel, locale, CommandArgs, message=None, guild=None, subcommand_attrs=None, slash_command=False):
        channel_id      = str(channel.id) if channel else None
        donator_profile = None
        dm = not bool(guild)
        subcommand_attrs = subcommand_attrs or {}

        if guild:
            if getattr(command, "addon", False):
                enabled_addons = guild and await get_enabled_addons(guild) or {}

                if str(command.addon) not in enabled_addons:
                    raise CancelCommand

                if getattr(command.addon, "premium", False):
                    donator_profile = await has_premium(guild=guild)

                    if "premium" not in donator_profile.features:
                        await response.error(f"This add-on requires premium! You may use `/donate` for instructions on donating.\n"
                                             f"You may also disable this add-on with `/addon change`.", hidden=True)

                        raise CancelCommand

            if RELEASE == "PRO" and command.name not in ("donate", "transfer", "eval", "status", "add-features", "stats"):
                if not donator_profile:
                    donator_profile = await has_premium(guild=guild)

                if "pro" not in donator_profile.features:
                    await response.error(f"Server not authorized to use Pro. Please use the `/donate` command to see information on "
                                          "how to get Bloxlink Pro.", hidden=True)

                    raise CancelCommand

            if not command.bypass_channel_perms:
                if command.premium_bypass_channel_perms and not donator_profile:
                    donator_profile = await has_premium(user=author)

                ignored_channels = await get_guild_value(guild, "ignoredChannels") or {}
                disabled_commands = await get_guild_value(guild, "disabledCommands") or {}

                author_perms = author.guild_permissions

                if guild.owner_id != author.id and not (author_perms.manage_guild or author_perms.administrator or discord.utils.find(lambda r: r.name in MAGIC_ROLES, author.roles) or (command.premium_bypass_channel_perms and "premium" in donator_profile.features)):
                    premium_upsell = "\n**Pro-tip:** Bloxlink Premium users can use this command in disabled channels! Learn more at https://patreon.com/bloxlink." if command.premium_bypass_channel_perms else ""
                    ignored_channel = ignored_channels.get(channel_id) or (channel.category and ignored_channels.get(str(channel.category.id)))
                    bypass_roles = ignored_channel.get("bypassRoles", []) if ignored_channel else []

                    if ignored_channel and not discord.utils.find(lambda r: str(r.id) in bypass_roles, author.roles):
                        await response.send(f"The server admins have **disabled** all commands in channel {channel.mention}.{premium_upsell}", dm=True, hidden=True, strict_post=True, no_dm_post=True)

                        if message:
                            try:
                                await message.delete()
                            except (discord.errors.Forbidden, discord.errors.NotFound):
                                pass

                        raise CancelCommand

                    if command.name in disabled_commands.get("global", []):
                        await response.send(f"The server admins have **disabled** the command `{command.name}` globally.{premium_upsell}", dm=True, hidden=True, strict_post=True, no_dm_post=True)

                        if message:
                            try:
                                await message.delete()
                            except (discord.errors.Forbidden, discord.errors.NotFound):
                                pass

                        raise CancelCommand

                    elif disabled_commands.get("channels", {}).get(channel_id, {}).get(command.name):
                        await response.send(f"The server admins have **disabled** the command `{command.name}` in channel {channel.mention}.{premium_upsell}", dm=True, hidden=True, strict_post=True, no_dm_post=True)

                        if message:
                            try:
                                await message.delete()
                            except (discord.errors.Forbidden, discord.errors.NotFound):
                                pass

                        raise CancelCommand

        restriction = await get_restriction("users", author.id)

        if restriction:
            restrction_text = isinstance(restriction, str) and f"has an active restriction for: `{restriction}`" or "has an active restriction from Bloxlink."

            await response.send(f"{author.mention} {restrction_text}", hidden=True)
            raise CancelCommand

        if command.cooldown and self.cache:
            redis_cooldown_key = f"cooldown_cache:{command.name}:{author.id}"

            if not donator_profile or (donator_profile and "premium" not in donator_profile.features):
                donator_profile = await has_premium(user=author)

            if "premium" not in donator_profile.features:
                on_cooldown = await self.cache.get(redis_cooldown_key)

                if on_cooldown:
                    cooldown_time = await self.redis.ttl(redis_cooldown_key)

                    embed = discord.Embed(title="Slow down!")
                    embed.description = "This command has a short cooldown since it's relatively expensive for the bot. " \
                                        f"You'll need to wait **{cooldown_time}** more second(s).\n\nDid you know? " \
                                        "**[Bloxlink Premium](https://www.patreon.com/join/bloxlink?)** subscribers NEVER " \
                                        "see any cooldowns. Find out more information with `/donate`."

                    m = await response.send(embed=embed, hidden=True)

                    if m:
                        await asyncio.sleep(10)

                        try:
                            await m.delete()

                            if message:
                                await message.delete()

                        except (discord.errors.NotFound, discord.errors.Forbidden):
                            pass

                    raise CancelCommand

                await self.cache.set(redis_cooldown_key, True, expire_time=command.cooldown)

        if not (command.dm_allowed or guild):
            await response.send("This command does not support DM. Please run it in a server.", hidden=True)
            raise CancelCommand

        try:
            await command.check_permissions(author, guild, locale, dm=dm, **subcommand_attrs)
        except PermissionError as e:
            if subcommand_attrs.get("allow_bypass"):
                CommandArgs.has_permission = False
            elif command.permissions.allow_bypass:
                CommandArgs.has_permission = False
            else:
                await response.error(e, hidden=True)
                raise CancelCommand

        except Message as e:
            message_type = "send" if e.type == "info" else e.type
            response_fn = getattr(response, message_type, response.send)

            if e.message:
                await response_fn(e, hidden=True)

            if subcommand_attrs.get("allow_bypass"):
                CommandArgs.has_permission = False
            elif command.permissions.allow_bypass:
                CommandArgs.has_permission = False
            else:
                raise CancelCommand

        else:
            CommandArgs.has_permission = True



    async def execute_command(self, command, fn, response, CommandArgs, author, channel, arguments, locale, guild=None, message=None, after_text="", slash_command=False):
        my_permissions = guild and guild.me.guild_permissions

        try:
            await arguments.initial_command_args(after_text)

            CommandArgs.add(prompt=arguments.prompt)
            response.prompt = arguments.prompt # pylint: disable=no-member

            await fn(CommandArgs)
        except PermissionError as e:
            if e.message:
                await response.error(e)
            else:
                await response.error(locale("permissions.genericError"))
        except discord.errors.Forbidden as e:
            if e.args:
                await response.error(e)
            else:
                await response.error(locale("permissions.genericError"))
        except RobloxAPIError:
            traceback.print_exc()
            await response.error("The Roblox API returned an error; are you supplying the correct ID to this command? Additionally, the Roblox API may also be down. Please try again later.")
        except RobloxDown:
            await response.error("The Roblox API is currently offline; please wait until Roblox is back online before re-running this command.")
        except CancelledPrompt as e:
            arguments.cancelled = True
            prompt_delete = await get_guild_value(guild, ["promptDelete", DEFAULTS.get("promptDelete")])

            if e.message:
                text = f"**{locale('prompt.cancelledPrompt')}:** {e}"
            else:
                text = f"**{locale('prompt.cancelledPrompt')}.**"

            if ((e.type == "delete" and not e.dm) and prompt_delete):
                if my_permissions and my_permissions.manage_messages:
                    if message:
                        try:
                            await message.delete()
                        except (discord.errors.Forbidden, discord.errors.NotFound):
                            pass

                    if slash_command and response.first_slash_command:
                        await response.first_slash_command.delete()
                else:
                    await response.send(text, dm=e.dm, no_dm_post=True)
            else:
                if my_permissions and my_permissions.manage_messages:
                    if slash_command and response.first_slash_command:
                        await response.first_slash_command.edit(content="**_Command finished._**", view=None, embed=None)

                await response.send(text, dm=e.dm, no_dm_post=True)

        except Message as e:
            message_type = "send" if e.type == "send" else e.type
            response_fn = getattr(response, message_type, response.send)

            if e.message:
                await response_fn(e, hidden=e.hidden)
            else:
                await response_fn("This command closed unexpectedly.")
        except Error as e:
            if e.message:
                await response.error(e, hidden=e.hidden)
            else:
                await response.error("This command has unexpectedly errored.")
        except CancelCommand as e:
            if e.message:
                await response.send(e, mention_author=True)
        except NotImplementedError:
            await response.error("The option you specified is currently not implemented, but will be coming soon!")
        except CancelledError:
            pass
        except Exception as e:
            """
            error_id = Bloxlink.error(e, command=command_name, user=(author.id, str(author)), guild=guild and f"id:{guild.id}")

            if error_id:
                await response.error("We've experienced an unexpected error. You may report this "
                                        f"error with ID `{error_id}` in our support server: {SERVER_INVITE}.")
            else:
                await response.error("An unexpected error occured.")
            """

            await response.error(locale("errors.commandError"))
            Bloxlink.error(traceback.format_exc(), title=f"Error source: {command.name}.py\n{f'Guild ID: {guild.id}' if guild else ''}")

        finally:
            delete_messages = response.delete_message_queue
            prompt_messages = arguments.messages
            bot_responses   = response.bot_responses

            if arguments.dm_post and not response.webhook_only:
                if arguments.cancelled:
                    content = f"{author.mention}, **this DM prompt has been cancelled.**"
                else:
                    content = f"{author.mention}, **this DM prompt has finished.**"

                try:
                    await arguments.dm_post.edit(content=content)
                except discord.errors.NotFound:
                    pass

            if my_permissions and my_permissions.manage_messages:
                delete_options = await get_guild_value(guild, ["promptDelete", DEFAULTS.get("promptDelete")], ["deleteCommands", DEFAULTS.get("deleteCommands")])

                delete_commands_after = delete_options["deleteCommands"]
                prompt_delete         = delete_options["promptDelete"]

                if prompt_delete:
                    if prompt_messages:
                        delete_messages += prompt_messages
                else:
                    delete_messages = [] # we'll populate this with the command information

                if delete_commands_after:
                    if message:
                        delete_messages.append(message.id)

                    delete_messages += bot_responses

                    await asyncio.sleep(delete_commands_after)

                if delete_messages:
                    if slash_command and response.first_slash_command and not arguments.cancelled:
                        await response.first_slash_command.edit(content="_**Command finished.**_", embed=None, view=None)

                    try:
                        await channel.purge(limit=100, check=lambda m: (m.id in delete_messages) or (delete_commands_after and re.search(f"^[</{command.name}:{slash_command}>]", m.content)))
                    except (discord.errors.Forbidden, discord.errors.HTTPException):
                        pass


    def slash_command_to_json(self, command):
        type_enums = {
            "string":  3,
            "number":  4,
            "boolean": 5,
            "user":    6,
            "channel": 7,
            "role":    8
        }

        def prompts_to_json(prompts):
            def single_prompt(prompt):
                option = {
                    "name": prompt["name"],
                    "type": type_enums.get(prompt.get("type", "string"), type_enums.get("string")),
                    "description": prompt.get("slash_desc", prompt["prompt"]),
                    "required": not (prompt.get("optional") or prompt.get("slash_optional")),
                    "choices": [{
                        "name": choice,
                        "value": choice

                    } for choice in prompt.get("choices", []) if len(prompt.get("choices", [])) <= 25 ],
                    "autocomplete": bool(prompt.get("auto_complete"))
                }

                return option

            if isinstance(prompts, dict):
                return single_prompt(prompts)
            else:
                return [single_prompt(prompt) for prompt in prompts]

        if command.slash_enabled:
            json = {
                "name": command.name,
                "description": command.description,
                "options": []
            }

            if command.subcommands:
                for subcommand_name, subcommand_fn in command.subcommands.items():
                    subcommand_attrs = getattr(subcommand_fn, "__subcommandattrs__")
                    subcommand_options = subcommand_attrs.get("slash_args") or subcommand_attrs.get("arguments")

                    json["options"].append({
                        "name": subcommand_name,
                        "type": 1,
                        "description": subcommand_attrs.get("slash_desc", subcommand_fn.__doc__),
                        "options": prompts_to_json(subcommand_options) if subcommand_options else None,
                    })

            elif command.slash_args or command.arguments:
                json["options"] += prompts_to_json(command.slash_args or command.arguments)


            return json


    def new_command(self, command_structure, addon=None):
        c = command_structure()
        command = Command(c)

        Bloxlink.log(f"Adding command {command.name}")

        if hasattr(c, "__setup__"):
            self.loop.create_task(c.__setup__())

        for attr_name in dir(command_structure):
            attr = getattr(c, attr_name)

            if callable(attr) and hasattr(attr, "__issubcommand__"):
                command.subcommands[attr_name] = attr

        self.commands[command.name] = command
        command.addon = addon

        self.loop.create_task(self.inject_command(command))

        return command_structure


    async def inject_command(self, command):
        subcommands = []

        if command.subcommands:
            for subcommand_name, subcommand in command.subcommands.items():
                subcommand_description = subcommand.__doc__ or "N/A"
                subcommands.append({"id": subcommand_name, "description": subcommand_description})

        if CLUSTER_ID == 0:
            if RELEASE == "MAIN":
                if not (command.addon or command.hidden):
                    await set_db_value("commands", command.name, **{
                        "description": command.description,
                        "usage": command.usage,
                        "category": command.category,
                        "hidden": command.hidden,
                        "subcommands": subcommands,
                        "slashCompatible": command.slash_enabled
                    })


    def app_command_to_json(self, application):
        return {
            "name": application.name,
            "type": application.type
        }

    def new_extension(self, application_structure):
        a = application_structure()
        app = Application(a)

        Bloxlink.log(f"Adding application {app.name}")

        if hasattr(a, "__setup__"):
            self.loop.create_task(a.__setup__())

        self.commands[app.name] = app

        return application_structure

    async def inject_extension(self, app):
        app_json = self.app_command_to_json(app)
        text, response = await fetch(COMMANDS_URL, "POST", body=app_json, headers={"Authorization": f"Bot {TOKEN}"}, raise_on_failure=False)

        if response.status not in (200, 201):
            Bloxlink.log(f"Extension {app.name} could not be added.")
            print(app, flush=True)
            print(response.status, text, flush=True)


    async def send_autocomplete_options(self, interaction, command_name, subcommand, command_args, focused_option):
        command = getattr(self, "commands").get(command_name)

        if command:
            if subcommand and command.subcommands.get(subcommand):
                fn = command.subcommands[subcommand]
                subcommand_attrs = getattr(fn, "__subcommandattrs__", {})
                prompts = subcommand_attrs.get("arguments")
            else:
                prompts = command.arguments

            prompt = discord.utils.find(lambda p: p["name"] == focused_option["name"], prompts)

            if prompt:
                try:
                    send_options = await prompt["auto_complete"](command.original_executable, interaction, command_args, focused_option["value"]) # subcommand
                except TypeError:
                    send_options = await prompt["auto_complete"](interaction, command_args, focused_option["value"])

                if send_options:
                    route = discord.http.Route("POST", "/interactions/{interaction_id}/{interaction_token}/callback", interaction_id=interaction.id, interaction_token=interaction.token)

                    payload = {
                        "type": 8,
                        "data": {
                            "choices": [
                                {
                                    "name": option[0] if isinstance(option, (list, tuple)) else option,
                                    "value": option[1] if isinstance(option, (list, tuple)) else option
                                } for option in send_options
                            ]
                        }
                    }

                    try:
                        await interaction.channel._state.http.request(route, json=payload)
                    except discord.errors.NotFound:
                        pass

    async def execute_interaction_command(self, typex, command_name, guild, channel, user, interaction, resolved=None, subcommand=None, arguments=None, forwarded=False, command_args=None):
        command = self.commands.get(command_name)

        if typex == "extensions" and not isinstance(command, Application):
            raise CancelCommand
        elif typex == "commands" and not isinstance(command, Command):
            raise CancelCommand

        if guild:
            guild_restriction = await get_restriction("guilds", guild.id)

            if guild_restriction:
                await guild.leave()
                raise CancelCommand

        if command:
            subcommand_attrs = {}

            if subcommand and command.subcommands.get(subcommand):
                fn = command.subcommands[subcommand]
                subcommand_attrs = getattr(fn, "__subcommandattrs__", None)
            else:
                fn = command.fn

            CommandArgs = Args(
                command_name = command_name,
                message = None,
                flags = {},
                has_permission = False,
                command = command,
                guild = guild,
                channel = channel,
                author = user,
                interaction = interaction,
                slash_command = True,
                resolved = resolved
            )

            CommandArgs.flags = {} if getattr(fn, "__flags__", False) else None # unsupported by slash commands

            locale = Locale("en")
            response = Response(CommandArgs, user, channel, guild, locale, interaction=interaction, forwarded=forwarded)

            if command_args:
                response.first_slash_command = getattr(command_args, "first_slash_command", response.first_slash_command)

            if Arguments.in_prompt(user):
                await response.send("You are currently in a prompt! Please complete it or say `cancel` to cancel.", hidden=True)
                raise CancelCommand

            CommandArgs.add(locale=locale, response=response)

            await self.command_checks(command=command, response=response, author=user, channel=channel, CommandArgs=CommandArgs, locale=locale, guild=guild, subcommand_attrs=subcommand_attrs, slash_command=True)

            if command.slash_defer and not forwarded:
                try:
                    await response.slash_defer(command.slash_ephemeral)
                except discord.NotFound:
                    raise CancelCommand

            arguments = Arguments(CommandArgs, user, channel, command, guild, None, subcommand=(subcommand, subcommand_attrs) if subcommand else None, slash_command=arguments)

            await self.execute_command(command=command, fn=fn, response=response, CommandArgs=CommandArgs, author=user, channel=channel, arguments=arguments, locale=locale, guild=guild, slash_command=True)
