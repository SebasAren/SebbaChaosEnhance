"""Pydantic models for PoE API responses."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StashTabProps(BaseModel):
    """A single stash tab's metadata from the tabs=1 response.

    The PoE endpoint returns abbreviated keys — ``n`` (name) and ``i`` (index)
    — so we alias those onto the friendlier field names. ``populate_by_name``
    keeps construction via ``name=``/``index=`` working too.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str = ""
    name: str = Field(default="", alias="n")
    type: str = ""  # "NormalStash", "CurrencyStash", "Folder", etc.
    index: int = Field(default=0, alias="i")
    children: list[StashTabProps] | None = None


class StashItem(BaseModel):
    """A single item in a stash tab."""

    id: str = ""
    name: str = ""  # prefix name (e.g. "Shaper's")
    typeLine: str = ""  # base type (e.g. "Gold Ring")
    ilvl: int = 0
    frameType: int = 0  # 0=Normal, 1=Magic, 2=Rare, 3=Unique
    identified: bool = False
    icon: str = ""
    category: dict = Field(default_factory=dict)
    socketedItems: list = Field(default_factory=list)
    influences: dict = Field(default_factory=dict)
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class StashTabContents(BaseModel):
    """Response from fetching individual tab contents."""

    numTabs: int = 0
    tabs: list[StashTabProps] | None = None
    items: list[StashItem] = Field(default_factory=list)


class StashTabMetadataResponse(BaseModel):
    """Response from the tabs=1 metadata request."""

    numTabs: int = 0
    tabs: list[StashTabProps] = Field(default_factory=list)
