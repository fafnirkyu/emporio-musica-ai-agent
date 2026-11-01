from app.policy import MINIMUM_SCORE, PolicyRetriever


def test_extracts_all_policy_pages():
    retriever = PolicyRetriever()

    assert len(retriever.pages) == 8
    assert [
        page["page_number"]
        for page in retriever.pages
    ] == list(range(1, 9))


def test_finds_online_return_policy():
    retriever = PolicyRetriever()

    result = retriever.search(
        "Posso devolver uma compra feita online?"
    )

    assert result["found"] is True
    assert result["matched_page"] == 4
    assert result["score"] >= MINIMUM_SCORE
    assert [
        page["page_number"]
        for page in result["pages"]
    ] == [3, 4, 5]


def test_finds_installment_policy():
    retriever = PolicyRetriever()

    result = retriever.search(
        "Posso pagar em 12 vezes?"
    )

    assert result["found"] is True
    assert result["matched_page"] == 3
    assert result["score"] >= MINIMUM_SCORE
    assert [
        page["page_number"]
        for page in result["pages"]
    ] == [2, 3, 4]


def test_handles_query_without_accents():
    retriever = PolicyRetriever()

    result = retriever.search(
        "Qual a regra para devolucao de compra online?"
    )

    assert result["found"] is True
    assert result["matched_page"] == 4


def test_rejects_unrelated_query():
    retriever = PolicyRetriever()

    result = retriever.search(
        "Escreva um algoritmo Python de ordenação"
    )

    assert result == {
        "found": False,
        "matched_page": None,
        "score": 0.0,
        "pages": [],
    }


def test_rejects_empty_query():
    retriever = PolicyRetriever()

    result = retriever.search("   ")

    assert result == {
        "found": False,
        "matched_page": None,
        "score": 0.0,
        "pages": [],
    }