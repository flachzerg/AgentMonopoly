import unittest

from app.api.games import _split_thought_chunks


class ThoughtStreamTests(unittest.TestCase):
    def test_split_thought_chunks_with_punctuation(self) -> None:
        text = "先看现金，再看地价，最后决定购买。"
        chunks = _split_thought_chunks(text, max_chunk_len=6)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual("".join(chunks), text)

    def test_split_thought_chunks_empty(self) -> None:
        self.assertEqual(_split_thought_chunks("", max_chunk_len=8), [])


if __name__ == "__main__":
    unittest.main()
