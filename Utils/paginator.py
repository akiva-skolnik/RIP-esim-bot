"""Paginator.py."""
# Source: https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/paginator.py
from typing import Any

import discord
from discord.ext import menus


class NumberedPageModal(discord.ui.Modal, title='Go to page'):
    """NumberedPageModal."""
    page = discord.ui.TextInput(label='Page', placeholder='Enter a number', min_length=1)

    def __init__(self, max_pages: int | None) -> None:
        super().__init__()
        self.interaction = None
        if max_pages is not None:
            as_string = str(max_pages)
            self.page.placeholder = f'Enter a number between 1 and {as_string}'
            self.page.max_length = len(as_string)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.interaction = interaction
        self.stop()


class Pages(discord.ui.View):
    """Pages."""

    def __init__(
            self,
            source: menus.PageSource,
            *,
            interaction: discord.Interaction,
            check_embeds: bool = True,
            compact: bool = True,
            embed: discord.Embed = discord.Embed(colour=discord.Colour.blurple())
    ):
        super().__init__()
        self.source: menus.PageSource = source
        self.interaction: discord.Interaction = interaction
        self.check_embeds: bool = check_embeds
        self.current_page: int = 0
        self.compact: bool = compact
        self.message = None
        self.embed: discord.Embed = embed
        self.clear_items()
        self.fill_items()

    def fill_items(self) -> None:
        """Fill_items."""
        if not self.compact:
            self.numbered_page.row = 1
            self.stop_pages.row = 1

        if self.source.is_paginating():
            max_pages = self.source.get_max_pages()
            use_last_and_first = max_pages is not None and max_pages >= 2
            if use_last_and_first:
                self.add_item(self.go_to_first_page)
            self.add_item(self.go_to_previous_page)
            if not self.compact:
                self.add_item(self.go_to_current_page)
            self.add_item(self.go_to_next_page)
            if use_last_and_first:
                self.add_item(self.go_to_last_page)
            if not self.compact:
                self.add_item(self.numbered_page)
            self.add_item(self.stop_pages)

    async def _get_kwargs_from_page(self, page: int) -> dict[str, Any]:
        value = await discord.utils.maybe_coroutine(self.source.format_page, self, page)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {'content': value, 'embed': None}
        if isinstance(value, discord.Embed):
            return {'embed': value, 'content': None}
        return {}

    async def show_page(self, interaction: discord.Interaction, page_number: int) -> None:
        """Show_page."""
        page = await self.source.get_page(page_number)
        self.current_page = page_number
        kwargs = await self._get_kwargs_from_page(page)
        self._update_labels(page_number)
        if kwargs:
            if interaction.response.is_done():
                if self.message:
                    await self.message.edit(**kwargs, view=self)
            else:
                await interaction.response.edit_message(**kwargs, view=self)

    def _update_labels(self, page_number: int) -> None:
        self.go_to_first_page.disabled = page_number == 0
        if self.compact:
            max_pages = self.source.get_max_pages()
            self.go_to_last_page.disabled = max_pages is None or (page_number + 1) >= max_pages
            self.go_to_next_page.disabled = max_pages is not None and (page_number + 1) >= max_pages
            self.go_to_previous_page.disabled = page_number == 0
            return

        self.go_to_current_page.label = str(page_number + 1)
        self.go_to_previous_page.label = str(page_number)
        self.go_to_next_page.label = str(page_number + 2)
        self.go_to_next_page.disabled = False
        self.go_to_previous_page.disabled = False
        self.go_to_first_page.disabled = False

        max_pages = self.source.get_max_pages()
        if max_pages is not None:
            self.go_to_last_page.disabled = (page_number + 1) >= max_pages
            if (page_number + 1) >= max_pages:
                self.go_to_next_page.disabled = True
                self.go_to_next_page.label = '…'
            if page_number == 0:
                self.go_to_previous_page.disabled = True
                self.go_to_previous_page.label = '…'

    async def show_checked_page(self, interaction: discord.Interaction, page_number: int) -> None:
        """Show_checked_page."""
        max_pages = self.source.get_max_pages()
        try:
            if max_pages is None:
                # If it doesn't give maximum pages, it cannot be checked
                await self.show_page(interaction, page_number)
            elif max_pages > page_number >= 0:
                await self.show_page(interaction, page_number)
        except IndexError:
            # An error happened that can be handled, so ignore it.
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.interaction.user.id:
            return True
        try:
            await interaction.followup.send('This pagination menu cannot be controlled by you, sorry!', ephemeral=True)
        except Exception:
            await interaction.user.send('This pagination menu cannot be controlled by you, sorry!')
        return False

    async def on_timeout(self) -> None:
        if self.message:
            await self.message.edit(view=None)

    async def start(self, *, content: str | None = None, ephemeral: bool = False, files=discord.utils.MISSING):
        """Start."""
        await self.source._prepare_once()
        page = await self.source.get_page(0)
        kwargs = await self._get_kwargs_from_page(page)
        if content:
            kwargs.setdefault('content', content)

        self._update_labels(0)
        func = self.interaction.followup.send if self.interaction.response.is_done()\
            else self.interaction.response.send_message
        self.message = await func(**kwargs, view=self, files=files, ephemeral=ephemeral)
        return self.message

    @discord.ui.button(label='≪', style=discord.ButtonStyle.grey)
    async def go_to_first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the first page."""
        await self.show_page(interaction, 0)

    @discord.ui.button(label='Back', style=discord.ButtonStyle.blurple)
    async def go_to_previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous page."""
        await self.show_checked_page(interaction, self.current_page - 1)

    @discord.ui.button(label='Current', style=discord.ButtonStyle.grey, disabled=True)
    async def go_to_current_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go_to_current_page."""

    @discord.ui.button(label='Next', style=discord.ButtonStyle.blurple)
    async def go_to_next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next page."""
        await self.show_checked_page(interaction, self.current_page + 1)

    @discord.ui.button(label='≫', style=discord.ButtonStyle.grey)
    async def go_to_last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the last page."""
        # The call here is safe because it's guarded by skip_if
        await self.show_page(interaction, self.source.get_max_pages() - 1)  # type: ignore

    @discord.ui.button(label='Skip to page...', style=discord.ButtonStyle.grey)
    async def numbered_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Lets you type a page number to go to."""
        if self.message is None:
            return

        modal = NumberedPageModal(self.source.get_max_pages())
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()

        if timed_out:
            await interaction.followup.send('Took too long', ephemeral=True)
            return
        if self.is_finished():
            await modal.interaction.response.send_message('Took too long', ephemeral=True)
            return

        value = str(modal.page.value)
        if not value.isdigit():
            await modal.interaction.response.send_message(f'Expected a number not {value!r}', ephemeral=True)
            return

        value = int(value)
        await self.show_checked_page(modal.interaction, value - 1)
        if not modal.interaction.response.is_done():
            error = modal.page.placeholder.replace('Enter', 'Expected')  # type: ignore # Can't be None
            await modal.interaction.response.send_message(error, ephemeral=True)

    @discord.ui.button(label='Delete', style=discord.ButtonStyle.red)
    async def stop_pages(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stops the pagination session."""
        # await interaction.delete_original_response()
        await self.message.delete()
        self.stop()


class FieldPageSource(menus.ListPageSource):
    """A page source that requires (field_name, field_value) tuple items."""

    def __init__(
            self,
            entries: list | tuple,
            *,
            per_page: int = 12,
            inline: bool = False,
            clear_description: bool = True,
            titles: list = None,
            embed: discord.Embed = discord.Embed(colour=discord.Colour.blurple())
    ) -> None:
        super().__init__(entries, per_page=per_page)
        self.embed: discord.Embed = embed
        self.clear_description: bool = clear_description
        self.inline: bool = inline
        self.titles: list = titles

    async def format_page(self, menu: Pages, page: list) -> discord.Embed:
        self.embed.clear_fields()
        self.embed.title = self.titles[menu.current_page] if self.titles else None
        if self.clear_description:
            self.embed.description = None

        # page can be a list of tuples or a list of lists (of tuples)
        # in the latter case, each inner list is a page
        if isinstance(page[0], list):
            page = page[menu.current_page]

        for key, value in page:
            self.embed.add_field(name=key, value=value, inline=self.inline)

        maximum = self.get_max_pages()
        if maximum > 1:
            if self.embed.footer.text and self.embed.footer.text.splitlines()[-1].startswith('Page'):
                self.embed.set_footer(text=self.embed.footer.text.rsplit('\n', 1)[0])
            self.embed.set_footer(text=(self.embed.footer.text or '') + f'\nPage {menu.current_page + 1}/{maximum}')

        return self.embed
