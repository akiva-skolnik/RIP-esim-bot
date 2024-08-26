from discord import ButtonStyle, Interaction, ui
from .utils import custom_followup


class Confirm(ui.View):
    """Confirm."""

    def __init__(self) -> None:
        super().__init__()
        self.value = None

    @ui.button(label='Confirm', style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: ui.Button) -> None:
        """Confirm."""
        self.value = True
        self.clear_items()
        self.stop()

    @ui.button(label='Cancel', style=ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: ui.Button) -> None:
        """Cancel."""
        self.value = False
        self.clear_items()
        self.stop()


class StopNext(ui.View):
    """Stop and next."""

    def __init__(self, interaction: Interaction) -> None:
        super().__init__()
        self.canceled = None
        self.next_page = None
        self.interaction = interaction
        self.next.disabled = False

    @ui.button(label='Next Page', style=ButtonStyle.blurple)
    async def next(self, interaction: Interaction, button: ui.Button) -> None:
        """Next Page."""
        self.next_page = True
        button.disabled = True
        await self.interaction.edit_original_response(view=self)
        await custom_followup(interaction, "Scanning more players...", ephemeral=True)
        self.stop()

    @ui.button(label='Stop', style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: ui.Button) -> None:
        """Cancel."""
        self.canceled = True
        self.clear_items()
        self.stop()


class Transform(ui.View):
    """Wait for next button."""

    def __init__(self) -> None:
        super().__init__()
        self.value = None

    @ui.button(label='Convert Ids', style=ButtonStyle.blurple)
    async def convert(self, interaction: Interaction, button: ui.Button) -> None:
        """Convert Ids."""
        await custom_followup(interaction, "Just a few moments...", ephemeral=True)
        self.value = True
        self.clear_items()
        self.stop()
