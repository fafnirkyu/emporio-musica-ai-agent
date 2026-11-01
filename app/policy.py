import re
from pathlib import Path

from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


POLICY_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "políticas_da_loja.pdf"
)

MINIMUM_SCORE = 0.05

PORTUGUESE_STOP_WORDS = [
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "essa",
    "esse",
    "esta",
    "este",
    "foi",
    "mais",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "posso",
    "qual",
    "quais",
    "que",
    "se",
    "sem",
    "sua",
    "seu",
    "um",
    "uma",
    "voce",
    "voces",
]


class PolicyRetriever:
    def __init__(self, policy_file=POLICY_FILE):
        self.pages = read_policy_pages(Path(policy_file))

        if not self.pages:
            raise ValueError(
                "No text could be extracted from the policy PDF"
            )

        self.vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            stop_words=PORTUGUESE_STOP_WORDS,
        )

        page_texts = [
            page["text"]
            for page in self.pages
        ]

        self.page_vectors = self.vectorizer.fit_transform(
            page_texts
        )

    def search(
        self,
        query,
        minimum_score=MINIMUM_SCORE,
    ):
        query = query.strip()

        if not query:
            return no_policy_match()

        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(
            query_vector,
            self.page_vectors,
        )[0]

        best_index = int(scores.argmax())
        best_score = float(scores[best_index])

        if best_score < minimum_score:
            return no_policy_match(best_score)

        first_page = max(0, best_index - 1)
        last_page = min(
            len(self.pages),
            best_index + 2,
        )

        return {
            "found": True,
            "matched_page": self.pages[best_index][
                "page_number"
            ],
            "score": round(best_score, 4),
            "pages": self.pages[first_page:last_page],
        }


def read_policy_pages(policy_file):
    reader = PdfReader(policy_file)
    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        text = clean_policy_text(
            page.extract_text() or ""
        )

        if text:
            pages.append(
                {
                    "page_number": page_number,
                    "text": text,
                }
            )

    return pages


def clean_policy_text(text):
    text = re.sub(
        (
            r"Empório\s+da\s+Música\s+"
            r"Manual\s+de\s+Políticas\s+e\s+"
            r"Procedimentos"
        ),
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"Página\s+\d+",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\b(\d+)x\b",
        r"\1 vezes",
        text,
        flags=re.IGNORECASE,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def no_policy_match(score=0.0):
    return {
        "found": False,
        "matched_page": None,
        "score": round(score, 4),
        "pages": [],
    }