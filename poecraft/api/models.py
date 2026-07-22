"""Pydantic models for PoE API responses."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StashTabProps(BaseModel):
    """A single stash tab's metadata from the tabs=1 response."""
    id: str = ""
    name: str = ""
    type: str = ""          # "NormalStash", "CurrencyStash", "Folder", etc.
    index: int = 0
    children: Optional[list[StashTabProps]] = None


class StashItem(BaseModel):
    """A single item in a stash tab."""
    id: str = ""
    name: str = ""          # prefix name (e.g. "Shaper's")
    typeLine: str = ""      # base type (e.g. "Gold Ring")
    ilvl: int = 0
    frameType: int = 0      # 0=Normal, 1=Magic, 2=Rare, 3=Unique
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
    tabs: Optional[list[StashTabProps]] = None
    items: list[StashItem] = Field(default_factory=list)


class StashTabMetadataResponse(BaseModel):
    """Response from the tabs=1 metadata request."""
    numTabs: int = 0
    tabs: list[StashTabProps] = Field(default_factory=list)
