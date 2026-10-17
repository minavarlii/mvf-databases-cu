// Must match the filter parts of HYBRID_SEARCH_SQL (article_id IN, ac., cat.) and LINKED_SEARCH_SQL (the
// article_links join and the source-title condition) in backend/app/db/queries/vector.py and the mock.
const FILTER_REF =
  /\b(article_id\s+IN|article_categories|categories|cat\.\w+|ac\.\w+|article_links|al\.\w+|source\.\w+|articles\s+AS\s+(?:source|target))\b/i

export function filterLines(sql: string): Set<number> {
  const marked = new Set<number>()
  sql.split('\n').forEach((line, i) => {
    if (FILTER_REF.test(line)) marked.add(i)
  })
  return marked
}
