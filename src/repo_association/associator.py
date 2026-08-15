"""
Paper -> GitHub repository association.

Policy (as agreed): a repository is associated with a paper ONLY when
explicit evidence establishes the relationship. Ranked by evidence_strength
(1=strongest):
  1. authoritative_paper_page  -- explicit link on the paper's own abs/project page
  2. trusted_metadata          -- explicit repo field from a trusted metadata source
  3. pwc_verified               -- explicit PapersWithCode association, author-submitted
  4. pwc_ai_agent_parsed        -- PWC association where the site's own docs indicate
                                    it was produced by AI-agent parsing, not human/author
                                    curation -- weakest tier, corroboration only

Never uses title similarity, org-name similarity, or star count to
establish or break a tie. If multiple candidates tie at the strongest
available tier, none is selected -- ambiguity is preserved.
"""
from __future__ import annotations

from src.models.schemas import RepoLinkCandidate


class RepoAssociator:
    def select_primary(self, candidates: list[RepoLinkCandidate]) -> RepoLinkCandidate | None:
        """Given all candidate links for one paper (already collected by
        upstream evidence-gathering steps, none fabricated here), decide
        whether exactly one can be defensibly selected."""
        if not candidates:
            return None

        strongest = min(c.evidence_strength for c in candidates)
        strongest_tier = [c for c in candidates if c.evidence_strength == strongest]

        if len(strongest_tier) == 1:
            return strongest_tier[0]

        # Multiple candidates tied at the strongest evidence tier.
        # Per policy: do NOT break the tie with stars/popularity.
        # If the source evidence itself explicitly labels one as
        # official/primary (e.g. locator text says "official implementation"),
        # that is still evidence-based and may be used -- but that labeling
        # must already be present in evidence_locator/evidence_text, not
        # inferred here. We check for that narrow, explicit signal only.
        explicitly_labeled = [
            c for c in strongest_tier
            if c.evidence_locator and "official" in c.evidence_locator.lower()
        ]
        if len(explicitly_labeled) == 1:
            return explicitly_labeled[0]

        # Still ambiguous -- preserve ambiguity, select nothing.
        return None
