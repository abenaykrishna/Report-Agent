import pandas as pd


class RelationshipService:
    """Infers candidate join relationships from discovered metadata.

    Uses multiple evidence signals to score each candidate edge:
      - same_column_name : column appears in >= 2 selected tables   (+base 0.65 or 0.55)
      - key_like         : column name ends with a FK/PK suffix      (+0.15)
      - type_match       : both sides share the same data_type       (+0.10)
      - not_null         : column is NOT NULL on both sides          (+0.05)

    Edges with composite confidence < CONFIDENCE_THRESHOLD are dropped
    so only credible join paths are forwarded to the SQL generator.

    The output DataFrame is auditable and can be used by downstream code
    to verify that generated SQL joins only approved column pairs.
    """

    # Key-like suffixes that strongly suggest a FK/PK column.
    KEY_HINTS = ("_id", "_no", "_key", "_code", "_ref", "id", "no")

    # Minimum composite confidence to include an edge in the output.
    CONFIDENCE_THRESHOLD = 0.60

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def infer_relationships(
        self,
        metadata_df: pd.DataFrame,
        selected_tables: list[str],
    ) -> pd.DataFrame:
        """Return a DataFrame of approved join edges for *selected_tables*.

        Each row represents a single directional edge:
          left_table.left_column  →  right_table.right_column

        Columns returned:
          left_dataset, left_table, left_column,
          right_dataset, right_table, right_column,
          confidence, evidence, join_type
        """
        if metadata_df.empty or not selected_tables:
            return pd.DataFrame(columns=self._columns())

        scoped = metadata_df[metadata_df["table_name"].isin(selected_tables)].copy()

        if scoped.empty or "column_name" not in scoped.columns:
            return pd.DataFrame(columns=self._columns())

        # Normalise nullable flag so we can use it as a boolean.
        if "is_nullable" in scoped.columns:
            scoped["_not_null"] = scoped["is_nullable"].str.upper() == "NO"
        else:
            scoped["_not_null"] = False

        relationships = []
        grouped = scoped.groupby("column_name", dropna=True)

        for column_name, rows in grouped:
            tables = (
                rows[["dataset_name", "table_name", "data_type", "_not_null"]]
                .drop_duplicates(subset=["dataset_name", "table_name"])
                .to_dict("records")
            )

            if len(tables) < 2:
                continue  # column must appear in at least two tables to form an edge

            for left_idx in range(len(tables)):
                for right_idx in range(left_idx + 1, len(tables)):
                    left = tables[left_idx]
                    right = tables[right_idx]

                    confidence, evidence = self._score_edge(
                        column_name,
                        left_dtype=left.get("data_type", ""),
                        right_dtype=right.get("data_type", ""),
                        left_not_null=bool(left.get("_not_null", False)),
                        right_not_null=bool(right.get("_not_null", False)),
                    )

                    if confidence < self.CONFIDENCE_THRESHOLD:
                        continue  # discard low-confidence edges

                    join_type = self._derive_join_type(
                        left_not_null=bool(left.get("_not_null", False)),
                        right_not_null=bool(right.get("_not_null", False)),
                    )

                    relationships.append({
                        "left_dataset":  left["dataset_name"],
                        "left_table":    left["table_name"],
                        "left_column":   column_name,
                        "right_dataset": right["dataset_name"],
                        "right_table":   right["table_name"],
                        "right_column":  column_name,
                        "confidence":    round(confidence, 2),
                        "evidence":      evidence,
                        "join_type":     join_type,
                    })

        if not relationships:
            return pd.DataFrame(columns=self._columns())

        result = pd.DataFrame(relationships, columns=self._columns())
        # Sort highest-confidence edges first so the LLM sees the best paths early.
        return result.sort_values("confidence", ascending=False).reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _score_edge(
        self,
        column_name: str,
        left_dtype: str,
        right_dtype: str,
        left_not_null: bool,
        right_not_null: bool,
    ) -> tuple[float, str]:
        """Return (composite_confidence, evidence_tag_string) for one edge."""
        evidence_tags: list[str] = []
        confidence: float = 0.0

        # Signal 1 — shared column name (always true here, so always add base score).
        is_key_like = self._is_key_like(column_name)
        if is_key_like:
            confidence += 0.80   # key-like column appearing in two tables is strong
            evidence_tags.append("same_name")
            evidence_tags.append("key_like")
        else:
            confidence += 0.65   # non-key shared name is a weaker signal
            evidence_tags.append("same_name")

        # Signal 2 — data type agreement.
        if left_dtype and right_dtype and left_dtype.upper() == right_dtype.upper():
            confidence = min(confidence + 0.10, 1.0)
            evidence_tags.append("type_match")

        # Signal 3 — both sides are NOT NULL (suggests a mandatory FK relationship).
        if left_not_null and right_not_null:
            confidence = min(confidence + 0.05, 1.0)
            evidence_tags.append("not_null")

        return confidence, ",".join(evidence_tags)

    def _is_key_like(self, column_name: str) -> bool:
        normalized = str(column_name).lower()
        return any(
            normalized.endswith(hint) or normalized == hint
            for hint in self.KEY_HINTS
        )

    @staticmethod
    def _derive_join_type(left_not_null: bool, right_not_null: bool) -> str:
        """Suggest a join type based on nullability of both sides."""
        if left_not_null and right_not_null:
            return "INNER"   # both columns mandatory — safe to inner join
        return "LEFT"        # at least one side may be absent — prefer left join

    @staticmethod
    def _columns() -> list[str]:
        return [
            "left_dataset",
            "left_table",
            "left_column",
            "right_dataset",
            "right_table",
            "right_column",
            "confidence",
            "evidence",
            "join_type",
        ]
