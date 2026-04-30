from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .paths import SCHEMA_DIR


@dataclass(frozen=True)
class EntityDefinition:
    id: str
    name: str
    aliases: list[str]
    entity_type: str
    description: str
    tags: list[str] = field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        seen: list[str] = []
        for value in [self.name, *self.aliases]:
            if value and value not in seen:
                seen.append(value)
        return seen


@dataclass(frozen=True)
class RelationDefinition:
    id: str
    label: str
    subject_types: list[str]
    object_types: list[str]
    patterns: list[str]
    subject_direction: str = "before"
    object_direction: str = "after"
    subject_tags: list[str] = field(default_factory=list)
    object_tags: list[str] = field(default_factory=list)
    negative_patterns: list[str] = field(default_factory=list)
    max_distance: int = 80
    symmetric: bool = False


@dataclass(frozen=True)
class DomainSchema:
    entity_types: list[str]
    entities: list[EntityDefinition]
    relations: list[RelationDefinition]
    central_entity_id: str | None = None

    @property
    def entity_by_id(self) -> dict[str, EntityDefinition]:
        return {entity.id: entity for entity in self.entities}


def load_domain_schema(path: Path | None = None) -> DomainSchema:
    schema_path = path or (SCHEMA_DIR / "turing_domain.json")
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    entities = [
        EntityDefinition(
            id=item["id"],
            name=item["name"],
            aliases=item.get("aliases", []),
            entity_type=item["type"],
            description=item.get("description", ""),
            tags=item.get("tags", []),
        )
        for item in payload["entities"]
    ]
    relations = [
        RelationDefinition(
            id=item["id"],
            label=item["label"],
            subject_types=item["subject_types"],
            object_types=item["object_types"],
            patterns=item["patterns"],
            subject_direction=item.get("subject_direction", "before"),
            object_direction=item.get("object_direction", "after"),
            subject_tags=item.get("subject_tags", []),
            object_tags=item.get("object_tags", []),
            negative_patterns=item.get("negative_patterns", []),
            max_distance=item.get("max_distance", 80),
            symmetric=item.get("symmetric", False),
        )
        for item in payload["relations"]
    ]
    return DomainSchema(
        entity_types=payload["entity_types"],
        entities=entities,
        relations=relations,
        central_entity_id=payload.get("central_entity_id"),
    )
