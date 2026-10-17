import { ApiError } from './errors'
import type {
  ApiClient,
  ArticleTitle,
  AskResponse,
  Category,
  Chunk,
  MariaDbDetails,
  PlanRow,
  SearchFilters,
  SearchRequest,
  SearchResponse,
  Stats,
} from './types'

// Mock triggers, typed into the question: !offline !db !llm !empty !noindex; with a filter set, !failhybrid (the filtered
// side, category or linked) / !failvector fail one compare side.
// Category Deep learning or Artificial intelligence matches nothing, as does a linked article with no MOCK_LINKS entry;
// ?nocategories / ?noarticles in the URL make api.categories() / api.articles() fail.
const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))

const MOCK_CHUNKS: Chunk[] = [
  {
    chunk_id: 3016,
    article_id: 206,
    article_title: 'Overfitting',
    article_url: 'https://en.wikipedia.org/wiki/Overfitting',
    chunk_index: 0,
    text: 'in mathematical modeling, overfitting is the production of an analysis that corresponds too closely or exactly to a particular set of data and may therefore fail to fit to additional data or predict future observations reliably. an overfitted model is a mathematical model that contains more parameters than can be justified by the data. in the special case of a model that consists of a polynomial function, these parameters represent the degree of a polynomial. the essence of overfitting is to unknowingly extract some of the residual variation ( i. e., noise ) as if that variation represents the underlying model structure. underfitting occurs when a mathematical model cannot adequately capture the underlying structure of the data. an under - fitted model is a model that is missing some parameters or terms that would appear in a correctly specified model. underfitting would occur, for example, when fitting a linear model to nonlinear data. such a model will tend to have poor predictive performance. the possibility of over - fitting exists when the criterion used for selecting the model is not the same as the criterion used to judge the',
    distance: 0.294,
  },
  {
    chunk_id: 3017,
    article_id: 206,
    article_title: 'Overfitting',
    article_url: 'https://en.wikipedia.org/wiki/Overfitting',
    chunk_index: 1,
    text: 'data. such a model will tend to have poor predictive performance. the possibility of over - fitting exists when the criterion used for selecting the model is not the same as the criterion used to judge the suitability of a model. for example, a model might be selected by maximizing its performance on some set of training data, yet its suitability might be determined by its ability to perform well on unseen data ; overfitting occurs when a model begins to " memorize " training data rather than " learning " to generalize from a trend. as an extreme example, if the number of parameters is the same as or greater than the number of observations, then a model can perfectly predict the training data simply by memorizing the data in its entirety. ( for an illustration, see figure 2. ) such a model will typically fail severely when making predictions. overfitting is related to both the complexity of the chosen model and how well it is optimized during training. a function class that is too large, in a suitable sense, relative to the dataset size is likely to over',
    distance: 0.317,
  },
  {
    chunk_id: 3028,
    article_id: 206,
    article_title: 'Overfitting',
    article_url: 'https://en.wikipedia.org/wiki/Overfitting',
    chunk_index: 12,
    text: 'therefore reduce over - fitting by probabilistically removing inputs to a layer. pruning is another technique that mitigates overfitting and enhances generalization by identifying a sparse, optimal neural network structure, while simultaneously reducing the computational cost of both training and inference. underfitting underfitting is the inverse of overfitting, meaning that the statistical model or machine learning algorithm is too simplistic to accurately capture the patterns in the data. a sign of underfitting is that there is a high bias and low variance detected in the current model or algorithm used ( the inverse of overfitting : low bias and high variance ). this can be gathered from the bias - variance tradeoff, which is the method of analyzing a model or algorithm for bias error, variance error, and irreducible error. with a high bias and low variance, the result of the model is that it will inaccurately represent the data points and thus insufficiently be able to predict future data results ( see generalization error ). as shown in figure 5, the linear line could not represent',
    distance: 0.322,
  },
  {
    chunk_id: 3033,
    article_id: 206,
    article_title: 'Overfitting',
    article_url: 'https://en.wikipedia.org/wiki/Overfitting',
    chunk_index: 17,
    text: '. 1. comparison of overfitting and overtraining " ( pdf ). journal of chemical information and modeling. 35 ( 5 ) : 826 – 833. doi : 10. 1021 / ci00027a006. further reading christian, brian ; griffiths, tom ( april 2017 ), " chapter 7 : overfitting ", algorithms to live by : the computer science of human decisions, william collins, pp. 149 – 168, isbn 978 - 0 - 00 - 754799 - 9 external links the problem of overfitting data – stony brook university what is " overfitting, " exactly? – andrew gelman blog cse546 : linear regression bias / variance tradeoff – university of washington what is underfitting – ibm',
    distance: 0.328,
  },
  {
    chunk_id: 1943,
    article_id: 131,
    article_title: 'Inductive probability',
    article_url: 'https://en.wikipedia.org/wiki/Inductive_probability',
    chunk_index: 4,
    text: '). { \\ displaystyle l ( a \\ land b ) = l ( b ) + l ( a | b ) = l ( a ) + l ( b | a ). } this means that if all the information is given describing an event then the length of the information may be used to give the raw probability of the event. so if the information describing the occurrence of a is given, along with the information describing b given a, then all the information describing a and b has been given. overfitting overfitting occurs when the model matches the random noise and not the pattern in the data. for example, take the situation where a curve is fitted to a set of points. if a polynomial with many terms is fitted then it can more closely represent the data. then the fit will be better, and the information needed to describe the deviations from the fitted curve will be smaller. smaller information length means higher probability. however, the information needed to describe the curve must also be considered. the total information for a curve with many terms may be greater than for a curve with',
    distance: 0.37,
  },
  {
    chunk_id: 2516,
    article_id: 168,
    article_title: 'Machine learning in earth sciences',
    article_url: 'https://en.wikipedia.org/wiki/Machine_learning_in_earth_sciences',
    chunk_index: 16,
    text: 'data since the 1970s. if one is interested in the yearly data, then only less than 50 samples are available. such amount of data may not be adequate. in a study of automatic classification of geological structures, the weakness of the model is the small training dataset, even though with the help of data augmentation to increase the size of the dataset. another study of predicting streamflow found that the accuracies depend on the availability of sufficient historical data, therefore sufficient training data determine the performance of machine learning. inadequate training data may lead to a problem called overfitting. overfitting causes inaccuracies in machine learning as the model learns about the noise and undesired details. limited by data input machine learning cannot carry out some of the tasks as a human does easily. for example, in the quantification of water inflow in rock tunnel faces by images for rock mass rating system ( rmr ), the damp and the wet state was not classified by machine learning because discriminating the two only by visual inspection is not possible. in some tasks, machine',
    distance: 0.434,
  },
  {
    chunk_id: 48,
    article_id: 1,
    article_title: 'Machine learning',
    article_url: 'https://en.wikipedia.org/wiki/Machine_learning',
    chunk_index: 47,
    text: 'interpretable ai, or explainable machine learning ( xml ), is artificial intelligence ( ai ) in which humans can understand the decisions or predictions made by the ai. it contrasts with the " black box " concept in machine learning where even its designers cannot explain why an ai arrived at a specific decision. by refining the mental models of users of ai - powered systems and dismantling their misconceptions, xai promises to help users perform more effectively. xai may be an implementation of the social right to explanation. overfitting settling on a bad, overly complex theory gerrymandered to fit all the past training data is known as overfitting. many systems attempt to reduce overfitting by rewarding a theory in accordance with how well it fits the data but penalising the theory in accordance with how complex the theory is. model collapse hallucinations hallucinations are different from knowingly deceiving : a model may generate an incorrect statement without having an intention, belief, or awareness of whether it is true or false. these can happen when a generative model produces',
    distance: 0.47,
  },
  {
    chunk_id: 860,
    article_id: 57,
    article_title: 'Data augmentation',
    article_url: 'https://en.wikipedia.org/wiki/Data_augmentation',
    chunk_index: 0,
    text: 'data augmentation is a statistical technique which allows maximum likelihood estimation from incomplete data. data augmentation has important applications in bayesian analysis, and the technique is widely used in machine learning to reduce overfitting when training machine learning models, achieved by training models on several slightly - modified copies of existing data. synthetic oversampling techniques for traditional machine learning synthetic minority over - sampling technique ( smote ) is a method used to address imbalanced datasets in machine learning. in such datasets, the number of samples in different classes varies significantly, leading to biased model performance. for example, in a medical diagnosis dataset with 90 samples representing healthy individuals and only 10 samples representing individuals with a particular disease, traditional algorithms may struggle to accurately classify the minority class. smote rebalances the dataset by generating synthetic samples for the minority class. for instance, if there are 100 samples in the majority class and 10 in the minority class, smote can create synthetic samples by randomly selecting a minority class sample and its nearest neighbors, then generating new samples along the line segments joining',
    distance: 0.544,
  },
  {
    chunk_id: 828,
    article_id: 55,
    article_title: 'Cross-validation (statistics)',
    article_url: 'https://en.wikipedia.org/wiki/Cross-validation_(statistics)',
    chunk_index: 30,
    text: 'can be misused : by performing an initial analysis to identify the most informative features using the entire data set – if feature selection or model tuning is required by the modeling procedure, this must be repeated on every training set. otherwise, predictions will certainly be upwardly biased. if cross - validation is used to decide which features to use, an inner cross - validation to carry out the feature selection on every training set must be performed. performing mean - centering, rescaling, dimensionality reduction, outlier removal or any other data - dependent preprocessing using the entire data set. while very common in practice, this has been shown to introduce biases into the cross - validation estimates. by allowing some of the training data to also be included in the test set – this can happen due to " twinning " in the data set, whereby some exactly identical or nearly identical samples are present in the data set, see pseudoreplication. to some extent twinning always takes place even in perfectly independent training and validation samples. this is because some of the training sample observations will have nearly',
    distance: 0.547,
  },
  {
    chunk_id: 554,
    article_id: 36,
    article_title: 'Bias–variance tradeoff',
    article_url: 'https://en.wikipedia.org/wiki/Bias%E2%80%93variance_tradeoff',
    chunk_index: 1,
    text: 'error from erroneous assumptions in the learning algorithm. high bias can cause an algorithm to miss the relevant relations between features and target outputs ( underfitting ). the variance is an error from sensitivity to small fluctuations in the training set. high variance may result from an algorithm modeling the random noise in the training data ( overfitting ). the bias – variance decomposition is a way of analyzing a learning algorithm\'s expected generalization error with respect to a particular problem as a sum of three terms, the bias, variance, and a quantity called the irreducible error, resulting from noise in the problem itself. motivation the bias – variance tradeoff is a central problem in supervised learning. ideally, one wants to choose a model that both accurately captures the regularities in its training data, but also generalizes well to unseen data. unfortunately, it is typically impossible to do both simultaneously. high - variance learning methods may be able to represent their training set well but are at risk of overfitting to noisy or unrepresentative training data. in contrast, algorithms with high bias typically',
    distance: 0.559,
  },
  {
    chunk_id: 2276,
    article_id: 148,
    article_title: 'Leakage (machine learning)',
    article_url: 'https://en.wikipedia.org/wiki/Leakage_(machine_learning)',
    chunk_index: 0,
    text: 'in statistics and machine learning, leakage ( also known as data leakage or target leakage ) refers to the use of information during model training that would not be available at prediction time. this results in overly optimistic performance estimates, as the model appears to perform better during evaluation than it actually would in a production environment. leakage is often subtle and indirect, making it difficult to detect and eliminate. it can lead a statistician or modeler to select a suboptimal model, which may be outperformed by a leakage - free alternative. leakage modes leakage can occur at multiple stages of the machine learning workflow. broadly, its sources can be divided into two categories : those arising from features and those arising from training examples. feature leakage feature or column - wise leakage is caused by the inclusion of columns which are one of the following : a duplicate label, a proxy for the label, or the label itself. these features, known as anachronisms, will not be available when the model is used for predictions, and result in leakage if included',
    distance: 0.571,
  },
]

const MOCK_ARTICLE_CATEGORIES: Record<number, string[]> = {
  206: ['Machine learning', 'Curve fitting', 'Statistical inference'],
  131: ['Machine learning', 'Inductive reasoning', 'Probability theory'],
  168: ['Machine learning', 'Geological techniques'],
  1: ['Machine learning', 'Learning', 'Cybernetics'],
  57: ['Machine learning'],
  55: ['Machine learning', 'Model selection'],
  36: ['Machine learning', 'Model selection', 'Statistical classification'],
  148: ['Machine learning', 'Statistical classification'],
}

// article_links targets per source title. Each source's snapshot in data/raw mentions these articles; ones with
// no targets here (e.g. Machine learning in earth sciences) show the empty linked result.
const MOCK_LINKS: Record<string, number[]> = {
  'Machine learning': [206, 55],
  Overfitting: [1, 55, 36],
  'Bias–variance tradeoff': [206, 1, 55],
  'Cross-validation (statistics)': [206, 1, 148],
}

// Real corpus titles, sorted like realApi.articles(); the ids of the chunk articles above match MOCK_CHUNKS.
const MOCK_ARTICLE_LIST: ArticleTitle[] = [
  { id: 2, title: 'Active learning (machine learning)' },
  { id: 3, title: 'Adversarial machine learning' },
  { id: 4, title: 'Anomaly detection' },
  { id: 5, title: 'Attention (machine learning)' },
  { id: 6, title: 'Automated machine learning' },
  { id: 36, title: 'Bias–variance tradeoff' },
  { id: 55, title: 'Cross-validation (statistics)' },
  { id: 57, title: 'Data augmentation' },
  { id: 131, title: 'Inductive probability' },
  { id: 148, title: 'Leakage (machine learning)' },
  { id: 1, title: 'Machine learning' },
  { id: 168, title: 'Machine learning in earth sciences' },
  { id: 206, title: 'Overfitting' },
]

function matchesFilters(chunk: Chunk, filters: SearchFilters | undefined): boolean {
  if (filters?.source_title) return (MOCK_LINKS[filters.source_title] ?? []).includes(chunk.article_id)
  if (filters?.category) return (MOCK_ARTICLE_CATEGORIES[chunk.article_id] ?? []).includes(filters.category)
  return true
}

const MOCK_CATEGORIES: Category[] = [
  { name: 'Artificial intelligence', article_count: 23 },
  { name: 'Deep learning', article_count: 16 },
  { name: 'Inductive reasoning', article_count: 4 },
  { name: 'Machine learning', article_count: 282 },
  { name: 'Model selection', article_count: 7 },
  { name: 'Statistical classification', article_count: 10 },
]

const MOCK_STATS: Stats = {
  article_count: 285,
  chunk_count: 3940,
  embedding_model: 'all-MiniLM-L6-v2',
  vector_dimensions: 384,
  mariadb_version: '11.8.9-MariaDB',
}

// LINKED_SEARCH_SQL in backend/app/db/queries/vector.py: the link join narrows the chunks before cosine ranking.
const LINKED_SQL = `SELECT
    c.id AS chunk_id,
    c.article_id,
    target.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    VEC_DISTANCE_COSINE(
        c.embedding,
        VEC_FromText(:embedding)
    ) AS distance
FROM article_links AS al
INNER JOIN articles AS source
    ON source.id = al.source_article_id
INNER JOIN articles AS target
    ON target.id = al.target_article_id
INNER JOIN chunks AS c
    ON c.article_id = target.id
WHERE source.title = :source_title
ORDER BY distance ASC
LIMIT :limit`

// Same shape as SEMANTIC_SEARCH_SQL / HYBRID_SEARCH_SQL in backend/app/db/queries/vector.py: the category
// filter narrows the chunks inside the vector ORDER BY ... LIMIT, so MariaDB can still use the vector index.
function buildSql(req: SearchRequest): string {
  if (req.filters?.source_title) return LINKED_SQL
  const whereSql = req.filters?.category
    ? `
    WHERE article_id IN (
        SELECT ac.article_id
        FROM article_categories AS ac
        INNER JOIN categories AS cat
            ON cat.id = ac.category_id
        WHERE cat.name = :category
    )`
    : ''

  return `SELECT
    c.chunk_id,
    c.article_id,
    a.title AS article_title,
    c.chunk_index,
    c.content,
    c.token_count,
    c.distance
FROM (
    SELECT
        id AS chunk_id,
        article_id,
        chunk_index,
        content,
        token_count,
        VEC_DISTANCE_COSINE(
            embedding,
            VEC_FromText(:embedding)
        ) AS distance
    FROM chunks${whereSql}
    ORDER BY distance ASC
    LIMIT :limit
) AS c
INNER JOIN articles AS a
    ON a.id = c.article_id
ORDER BY c.distance ASC`
}

// Shaped like the live backend's EXPLAIN for the queries above (linked: experiments/results/search_strategies.json).
function buildPlan(req: SearchRequest, bruteForce: boolean): PlanRow[] {
  const f = req.filters ?? {}
  if (f.source_title) {
    const simple = (table: string, access_type: string, key: string, rows: number, extra = ''): PlanRow => ({
      select_id: 1,
      select_type: 'SIMPLE',
      table,
      access_type,
      key,
      rows,
      extra,
    })
    return [
      simple('source', 'ref', 'ix_articles_title', 1, 'Using where; Using index; Using temporary; Using filesort'),
      simple('al', 'ref', 'PRIMARY', 10),
      simple('target', 'eq_ref', 'PRIMARY', 1),
      simple('c', 'ref', 'ix_chunks_article_id', 10),
    ]
  }
  const derived = (table: string, access_type: string, key: string | null, rows: number, extra = ''): PlanRow => ({
    select_id: 2,
    select_type: 'DERIVED',
    table,
    access_type,
    key,
    rows,
    extra,
  })
  return [
    { select_id: 1, select_type: 'PRIMARY', table: '<derived2>', access_type: 'ALL', key: null, rows: 5, extra: 'Using filesort' },
    { select_id: 1, select_type: 'PRIMARY', table: 'a', access_type: 'eq_ref', key: 'PRIMARY', rows: 1, extra: '' },
    ...(f.category ? [derived('cat', 'const', 'uq_categories_name', 1, 'Using index')] : []),
    bruteForce
      ? derived('chunks', 'ALL', null, 3940, 'Using where; Using filesort')
      : derived('chunks', 'index', 'ix_chunks_embedding', 3185),
    ...(f.category ? [derived('ac', 'eq_ref', 'fk_article_categories_category', 1, 'Using index')] : []),
  ]
}

// Plain and category searches use the vector index (only !noindex shows brute force); linked search is
// relational-first, as on the real backend, so it reads chunks through ix_chunks_article_id instead.
function details(req: SearchRequest, chunkCount: number, totalMs: number): MariaDbDetails {
  const linked = Boolean(req.filters?.source_title)
  const bruteForce = req.question.includes('!noindex')
  const searchMs = linked ? 86.2 : bruteForce ? 234.6 : req.filters?.category ? 8.5 : 7.1
  return {
    sql: buildSql(req),
    query_plan: buildPlan(req, bruteForce),
    search_latency_ms: searchMs,
    total_response_ms: totalMs + Math.round(searchMs - 7.1),
    chunk_count: chunkCount,
    vector_index_used: !linked && !bruteForce,
  }
}

async function runSearch(req: SearchRequest): Promise<SearchResponse> {
  await delay(500)
  const q = req.question

  if (q.includes('!offline')) throw new ApiError('BACKEND_UNAVAILABLE', 'Mock: backend offline')
  if (q.includes('!db')) throw new ApiError('DATABASE_UNAVAILABLE', 'Mock: database down')

  const chunks = q.includes('!empty')
    ? []
    : MOCK_CHUNKS.filter((c) => matchesFilters(c, req.filters)).slice(0, req.top_k ?? 5)
  return { chunks, details: details(req, chunks.length, 520) }
}

export const mockApi: ApiClient = {
  capabilities: {
    filters: { category: true, source_title: true },
  },

  async search(req) {
    if (req.filters?.category && req.filters.source_title) {
      throw new ApiError('BAD_REQUEST', 'One filter at a time: category or linked article.')
    }
    const filtered = Object.keys(req.filters ?? {}).length > 0
    if (req.question.includes(filtered ? '!failhybrid' : '!failvector')) {
      await delay(300)
      const side = req.filters?.source_title ? 'linked' : filtered ? 'hybrid' : 'vector-only'
      throw new ApiError('DATABASE_UNAVAILABLE', `Mock: ${side} search failed`)
    }
    return runSearch(req)
  },

  async ask(req): Promise<AskResponse> {
    const result = await runSearch(req)
    if (result.chunks.length === 0) return { ...result, answer: '', sources: [] }

    await delay(900)

    if (req.question.includes('!llm')) throw new ApiError('LLM_FAILED', 'Mock: LLM failed')

    const seen = new Map<number, { article_id: number; title: string; url: string }>()
    for (const c of result.chunks) {
      if (!seen.has(c.article_id)) {
        seen.set(c.article_id, { article_id: c.article_id, title: c.article_title, url: c.article_url })
      }
    }

    return {
      ...result,
      answer:
        'Overfitting is when a model fits its training data too closely, so it fails on new data and can’t predict future observations reliably [1]. It typically happens when a model has more parameters than the data can justify and starts treating noise as if it were real structure [1][5]: the model memorizes the training data instead of learning to generalize from the trend [2]. The opposite, underfitting, is a model too simple to capture the patterns, with high bias and low variance; randomly dropping inputs to a layer (dropout) and pruning the network both reduce overfitting [3].',
      sources: [...seen.values()],
      details: { ...result.details, total_response_ms: result.details.total_response_ms + 910 },
    }
  },

  async categories() {
    await delay(200)
    if (new URLSearchParams(window.location.search).has('nocategories')) {
      throw new ApiError('BACKEND_UNAVAILABLE', 'Mock: categories unavailable')
    }
    return MOCK_CATEGORIES
  },

  async articles() {
    await delay(300)
    if (new URLSearchParams(window.location.search).has('noarticles')) {
      throw new ApiError('BACKEND_UNAVAILABLE', 'Mock: articles unavailable')
    }
    return MOCK_ARTICLE_LIST
  },

  async stats() {
    await delay(200)
    return MOCK_STATS
  },
}