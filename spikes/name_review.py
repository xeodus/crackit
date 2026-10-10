"""Name suggestions preserve recognizer text and require explicit entity confirmation."""
from dataclasses import dataclass
from typing import Tuple,Optional
import unicodedata

def folded(text):return unicodedata.normalize('NFC',text).casefold()

def distance(left,right):
    prior=list(range(len(right)+1))
    for i,a in enumerate(left,1):
        row=[i]
        for j,b in enumerate(right,1):row.append(min(row[-1]+1,prior[j]+1,prior[j-1]+(a!=b)))
        prior=row
    return prior[-1]

@dataclass(frozen=True)
class NameReview:
    observed: str
    candidates: Tuple[str,...]
    confirmed_entity: Optional[str]
    requires_confirmation: bool
    reason: str

def review_name(observed,roster,confirmed_entity=None):
    """Confirmation is an explicit user binding, never a model spelling correction.

    Even an exact roster spelling is unverified: Mira/Meera can sound alike.
    Suggestions are spelling distance only; they do not establish identity.
    Unknown names remain valid literal spans and are never replaced.
    """
    if not observed.strip():raise ValueError('Observed name is required')
    if confirmed_entity is not None and confirmed_entity not in roster:
        raise ValueError('Confirmation must reference an explicit roster entity')
    candidates=tuple(sorted((name for name in roster if distance(folded(observed),folded(name))<=2),
                            key=lambda n:(distance(folded(observed),folded(n)),folded(n))))
    return NameReview(observed,candidates,confirmed_entity,confirmed_entity is None,
                      'Explicit binding supplied' if confirmed_entity else 'Spelling resemblance cannot establish action ownership')
