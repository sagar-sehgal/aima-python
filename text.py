"""Statistical Language Processing tools.  (Chapter 22)
We define Unigram and Ngram text models, use them to generate random text,
and show the Viterbi algorithm for segmentatioon of letters into words.
Then we show a very simple Information Retrieval system, and an example
working on a tiny sample of Unix manual pages."""

from utils import argmin, argmax, hashabledict
from learning import CountingProbDist
import search

from math import log, exp
from collections import defaultdict
import heapq
import re
import os


class UnigramWordModel(CountingProbDist):

    """This is a discrete probability distribution over words, so you
    can add, sample, or get P[word], just like with CountingProbDist. You can
    also generate a random text, n words long, with P.samples(n)."""

    def __init__(self, observations, default=0):
        # Call CountingProbDist constructor,
        # passing the observations and default parameters.
        super(UnigramWordModel, self).__init__(observations, default)

    def samples(self, n):
        """Return a string of n words, random according to the model."""
        return ' '.join(self.sample() for i in range(n))


class NgramWordModel(CountingProbDist):

    """This is a discrete probability distribution over n-tuples of words.
    You can add, sample or get P[(word1, ..., wordn)]. The method P.samples(n)
    builds up an n-word sequence; P.add_cond_prob and P.add_sequence add data."""

    def __init__(self, n, observation_sequence=None, default=0):
        # In addition to the dictionary of n-tuples, cond_prob is a
        # mapping from (w1, ..., wn-1) to P(wn | w1, ... wn-1)
        CountingProbDist.__init__(self, default=default)
        self.n = n
        self.cond_prob = defaultdict()
        self.add_sequence(observation_sequence or [])

    # __getitem__, top, sample inherited from CountingProbDist
    # Note that they deal with tuples, not strings, as inputs

    def add_cond_prob(self, ngram):
        """Build the conditional probabilities P(wn | (w1, ..., wn-1)"""
        if ngram[:-1] not in self.cond_prob:
            self.cond_prob[ngram[:-1]] = CountingProbDist()
        self.cond_prob[ngram[:-1]].add(ngram[-1])

    def add_sequence(self, words):
        """Add each tuple words[i:i+n], using a sliding window."""
        n = self.n

        for i in range(len(words) - n + 1):
            t = tuple(words[i:i + n])
            self.add(t)
            self.add_cond_prob(t)

    def samples(self, nwords):
        """Generate an n-word sentence by picking random samples
        according to the model. At first pick a random n-gram and
        from then on keep picking a character according to
        P(c|wl-1, wl-2, ..., wl-n+1) where wl-1 ... wl-n+1 are the
        last n - 1 words in the generated sentence so far."""
        n = self.n
        output = list(self.sample())

        for i in range(n, nwords):
            last = output[-n+1:]
            next_word = self.cond_prob[tuple(last)].sample()
            output.append(next_word)

        return ' '.join(output)


class NgramCharModel(NgramWordModel):
    def add_sequence(self, words):
        """Add an empty space to every word to catch the beginning of words."""
        for word in words:
            super().add_sequence(' ' + word)


class UnigramCharModel(NgramCharModel):
    def __init__(self, observation_sequence=None, default=0):
        CountingProbDist.__init__(self, default=default)
        self.n = 1
        self.cond_prob = defaultdict()
        self.add_sequence(observation_sequence or [])

    def add_sequence(self, words):
        for word in words:
            for char in word:
                self.add(char)

# ______________________________________________________________________________


def viterbi_segment(text, P):
    """Find the best segmentation of the string of characters, given the
    UnigramWordModel P."""
    # best[i] = best probability for text[0:i]
    # words[i] = best word ending at position i
    n = len(text)
    words = [''] + list(text)
    best = [1.0] + [0.0] * n
    # Fill in the vectors best words via dynamic programming
    for i in range(n+1):
        for j in range(0, i):
            w = text[j:i]
            curr_score = P[w] * best[i - len(w)]
            if curr_score >= best[i]:
                best[i] = curr_score
                words[i] = w
    # Now recover the sequence of best words
    sequence = []
    i = len(words) - 1
    while i > 0:
        sequence[0:0] = [words[i]]
        i = i - len(words[i])
    # Return sequence of best words and overall probability
    return sequence, best[-1]


# ______________________________________________________________________________


# TODO(tmrts): Expose raw index
class IRSystem:

    """A very simple Information Retrieval System, as discussed in Sect. 23.2.
    The constructor s = IRSystem('the a') builds an empty system with two
    stopwords. Next, index several documents with s.index_document(text, url).
    Then ask queries with s.query('query words', n) to retrieve the top n
    matching documents. Queries are literal words from the document,
    except that stopwords are ignored, and there is one special syntax:
    The query "learn: man cat", for example, runs "man cat" and indexes it."""

    def __init__(self, stopwords='the a of'):
        """Create an IR System. Optionally specify stopwords."""
        # index is a map of {word: {docid: count}}, where docid is an int,
        # indicating the index into the documents list.
        self.index = defaultdict(lambda: defaultdict(int))
        self.stopwords = set(words(stopwords))
        self.documents = []

    def index_collection(self, filenames):
        """Index a whole collection of files."""
        prefix = os.path.dirname(__file__)
        for filename in filenames:
            self.index_document(open(filename).read(),
                                os.path.relpath(filename, prefix))

    def index_document(self, text, url):
        """Index the text of a document."""
        # For now, use first line for title
        title = text[:text.index('\n')].strip()
        docwords = words(text)
        docid = len(self.documents)
        self.documents.append(Document(title, url, len(docwords)))
        for word in docwords:
            if word not in self.stopwords:
                self.index[word][docid] += 1

    def query(self, query_text, n=10):
        """Return a list of n (score, docid) pairs for the best matches.
        Also handle the special syntax for 'learn: command'."""
        if query_text.startswith("learn:"):
            doctext = os.popen(query_text[len("learn:"):], 'r').read()
            self.index_document(doctext, query_text)
            return []

        qwords = [w for w in words(query_text) if w not in self.stopwords]
        shortest = argmin(qwords, key=lambda w: len(self.index[w]))
        docids = self.index[shortest]
        return heapq.nlargest(n, ((self.total_score(qwords, docid), docid) for docid in docids))

    def score(self, word, docid):
        """Compute a score for this word on the document with this docid."""
        # There are many options; here we take a very simple approach
        return (log(1 + self.index[word][docid]) /
                log(1 + self.documents[docid].nwords))

    def total_score(self, words, docid):
        """Compute the sum of the scores of these words on the document with this docid."""
        return sum(self.score(word, docid) for word in words)

    def present(self, results):
        """Present the results as a list."""
        for (score, docid) in results:
            doc = self.documents[docid]
            print(
                ("{:5.2}|{:25} | {}".format(100 * score, doc.url,
                                            doc.title[:45].expandtabs())))

    def present_results(self, query_text, n=10):
        """Get results for the query and present them."""
        self.present(self.query(query_text, n))


class UnixConsultant(IRSystem):

    """A trivial IR system over a small collection of Unix man pages."""

    def __init__(self):
        IRSystem.__init__(self, stopwords="how do i the a of")

        import os
        aima_root = os.path.dirname(__file__)
        mandir = os.path.join(aima_root, 'aima-data/MAN/')
        man_files = [mandir + f for f in os.listdir(mandir)
                     if f.endswith('.txt')]

        self.index_collection(man_files)


class Document:

    """Metadata for a document: title and url; maybe add others later."""

    def __init__(self, title, url, nwords):
        self.title = title
        self.url = url
        self.nwords = nwords


def words(text, reg=re.compile('[a-z0-9]+')):
    """Return a list of the words in text, ignoring punctuation and
    converting everything to lowercase (to canonicalize).
    >>> words("``EGAD!'' Edgar cried.")
    ['egad', 'edgar', 'cried']
    """
    return reg.findall(text.lower())


def canonicalize(text):
    """Return a canonical text: only lowercase letters and blanks.
    >>> canonicalize("``EGAD!'' Edgar cried.")
    'egad edgar cried'
    """
    return ' '.join(words(text))


# ______________________________________________________________________________

# Example application (not in book): decode a cipher.
# A cipher is a code that substitutes one character for another.
# A shift cipher is a rotation of the letters in the alphabet,
# such as the famous rot13, which maps A to N, B to M, etc.

alphabet = 'abcdefghijklmnopqrstuvwxyz'

# Encoding


def shift_encode(plaintext, n):
    """Encode text with a shift cipher that moves each letter up by n letters.
    >>> shift_encode('abc z', 1)
    'bcd a'
    """
    return encode(plaintext, alphabet[n:] + alphabet[:n])


def rot13(plaintext):
    """Encode text by rotating letters by 13 spaces in the alphabet.
    >>> rot13('hello')
    'uryyb'
    >>> rot13(rot13('hello'))
    'hello'
    """
    return shift_encode(plaintext, 13)


def translate(plaintext, function):
    """Translate chars of a plaintext with the given function."""
    result = ""
    for char in plaintext:
        result += function(char)
    return result


def maketrans(from_, to_):
    """Create a translation table and return the proper function."""
    trans_table = {}
    for n, char in enumerate(from_):
        trans_table[char] = to_[n]

    return lambda char: trans_table.get(char, char)


def encode(plaintext, code):
    """Encode text using a code which is a permutation of the alphabet."""
    trans = maketrans(alphabet + alphabet.upper(), code + code.upper())

    return translate(plaintext, trans)


def bigrams(text):
    """Return a list of pairs in text (a sequence of letters or words).
    >>> bigrams('this')
    ['th', 'hi', 'is']
    >>> bigrams(['this', 'is', 'a', 'test'])
    [['this', 'is'], ['is', 'a'], ['a', 'test']]
    """
    return [text[i:i + 2] for i in range(len(text) - 1)]

# Decoding a Shift (or Caesar) Cipher


class ShiftDecoder:

    """There are only 26 possible encodings, so we can try all of them,
    and return the one with the highest probability, according to a
    bigram probability distribution."""

    def __init__(self, training_text):
        training_text = canonicalize(training_text)
        self.P2 = CountingProbDist(bigrams(training_text), default=1)

    def score(self, plaintext):
        """Return a score for text based on how common letters pairs are."""

        s = 1.0
        for bi in bigrams(plaintext):
            s = s * self.P2[bi]

        return s

    def decode(self, ciphertext):
        """Return the shift decoding of text with the best score."""

        return argmax(all_shifts(ciphertext), key=lambda shift: self.score(shift))


def all_shifts(text):
    """Return a list of all 26 possible encodings of text by a shift cipher."""

    yield from (shift_encode(text, i) for i, _ in enumerate(alphabet))

# Decoding a General Permutation Cipher


class PermutationDecoder:

    """This is a much harder problem than the shift decoder. There are 26!
    permutations, so we can't try them all. Instead we have to search.
    We want to search well, but there are many things to consider:
    Unigram probabilities (E is the most common letter); Bigram probabilities
    (TH is the most common bigram); word probabilities (I and A are the most
    common one-letter words, etc.); etc.
    We could represent a search state as a permutation of the 26 letters,
    and alter the solution through hill climbing. With an initial guess
    based on unigram probabilities, this would probably fare well. However,
    I chose instead to have an incremental representation. A state is
    represented as a letter-to-letter map; for example {'z': 'e'} to
    represent that 'z' will be translated to 'e'."""

    def __init__(self, training_text, ciphertext=None):
        self.Pwords = UnigramWordModel(words(training_text))
        self.P1 = UnigramWordModel(training_text)  # By letter
        self.P2 = NgramWordModel(2, words(training_text))  # By letter pair

    def decode(self, ciphertext):
        """Search for a decoding of the ciphertext."""
        self.ciphertext = canonicalize(ciphertext)
        # reduce domain to speed up search
        self.chardomain = {c for c in self.ciphertext if c != ' '}
        problem = PermutationDecoderProblem(decoder=self)
        solution = search.best_first_graph_search(
            problem, lambda node: self.score(node.state))

        solution.state[' '] = ' '
        return translate(self.ciphertext, lambda c: solution.state[c])

    def score(self, code):
        """Score is product of word scores, unigram scores, and bigram scores.
        This can get very small, so we use logs and exp."""

        # remake code dictionary to contain translation for all characters
        full_code = code.copy()
        full_code.update({x: x for x in self.chardomain if x not in code})
        full_code[' '] = ' '
        text = translate(self.ciphertext, lambda c: full_code[c])

        # add small positive value to prevent computing log(0)
        # TODO: Modify the values to make score more accurate
        logP = (sum(log(self.Pwords[word] + 1e-20) for word in words(text)) +
                sum(log(self.P1[c] + 1e-5) for c in text) +
                sum(log(self.P2[b] + 1e-10) for b in bigrams(text)))
        return -exp(logP)


class PermutationDecoderProblem(search.Problem):

    def __init__(self, initial=None, goal=None, decoder=None):
        self.initial = initial or hashabledict()
        self.decoder = decoder

    def actions(self, state):
        search_list = [c for c in self.decoder.chardomain if c not in state]
        target_list = [c for c in alphabet if c not in state.values()]
        # Find the best charater to replace
        plainchar = argmax(search_list, key=lambda c: self.decoder.P1[c])
        for cipherchar in target_list:
            yield (plainchar, cipherchar)

    def result(self, state, action):
        new_state = hashabledict(state)  # copy to prevent hash issues
        new_state[action[0]] = action[1]
        return new_state

    def goal_test(self, state):
        """We're done when all letters in search domain are assigned."""
        return len(state) >= len(self.decoder.chardomain)


#-----------------------------TF-IDF--------------------------------------
class tf_idf_analysis:
    '''a class to perform tf-idf analysis on a given set of documents and also search a query'''
#     class variabels(their type)= values contained in the variable
#     docs(list)=contains all the documents
#     terms_tf_idf_score(list of dict)=tf-idf-score of all the documents with all words
#     doc_tf(list of dict)=a list containting the tf of each word in each document
#     terms_df(dict of list)= gives the df of ach term
    def __init__(self,docs):
        '''input: list of all documents'''
        self.docs=docs
        self.tf_idf_score=self.make_tf_idf()
    def make_tf_idf(self):
        '''makes the tf-idf score of all the words in all the documents'''
        terms_df={}
        doc_tf=[]
        counter=0
        for i in self.docs:
            counter+=1
            tf=self.get_term_frequency(i)
            doc_tf.append(tf)
            for j in tf.items():
                if(terms_df.get(j[0],None)==None):
                    terms_df[j[0]]=[counter]
                elif(i not in terms_df[j[0]]):
                    terms_df[j[0]].append(counter)
        terms_tf_idf_score=[]
        for i in doc_tf:
            x={}
            for j in i.items():
                x[j[0]]=self.tf_mul_idf(j[1],len(terms_df.get(j[0],[])))
            terms_tf_idf_score.append(x)
        self.terms_tf_idf_score=terms_tf_idf_score
        self.doc_tf=doc_tf
        self.terms_df=terms_df
        return terms_tf_idf_score
    def tf_mul_idf(self,tf,df):
        '''multiplies the term frequency and inter-docuemt frequency to give the correct score'''
        return math.log(1+tf)*math.log(len(self.docs)/(1+df))
    def get_term_frequency(self,doc):
        '''returns a dictionary containing the frequency of each term in a given document'''
        term_freq={}
        total_terms=0
        for i in doc.split():
            total_terms+=1
            if(term_freq.get(i,0)==0):
                term_freq[i]=1
            else:
                term_freq[i]+=1
        for i,j in term_freq.items():
            term_freq[i]=j/total_terms
        return term_freq
    def get_doc_no(self,doc):
        '''gets the document number of a given document from the list of docuemnts given '''
        counter=0
        for i in self.docs:
            if(i==doc):
                return counter
            counter+=1
    def get_tf_idf_score(self,word,doc):
        '''returns the tf-idf score of the document '''
        doc_no=self.get_doc_no(doc)
        return self.terms_tf_idf_score[doc_no].get(word,0)
    def top(self,doc,n):
        '''returns top n most important word of that document'''
        doc_no=self.get_doc_no(doc)
        x=self.terms_tf_idf_score[doc_no]
        return sorted(x.items(),key=lambda z:z[1],reverse=True)[:n]
    def get_tf_idf_vector(self,doc):
        '''returns the tf-idf vector of the document'''
        tf=self.get_term_frequency(doc)
        vector={}
        for i in doc.split():
            vector[i]=self.tf_mul_idf(tf.get(i,0),len(self.terms_df.get(i,[])))
        return vector
    def search_query(self,query):
        '''returns the sorted list of all the relevant docuemnts along with their relevance scores'''
        queryvec=self.get_tf_idf_vector(query)
        doc_score={}
        query_mag=math.sqrt(sum([j[1]**2 for j in queryvec.items()]))
        for i in range(len(self.docs)):
            common_words=[j for j in query.split() if j in self.docs[i].split()]
            if(len(common_words)==0):
                doc_score[i]=0
            else:
                dot_product=sum([queryvec[j]*self.terms_tf_idf_score[i][j] for j in common_words])
                doc_mag=math.sqrt(sum([j[1]**2 for j in self.terms_tf_idf_score[i].items()]))
                doc_score[i]=dot_product/(query_mag*doc_mag)
        sorted_doc_score=sorted(doc_score.items(),key=lambda x:x[1],reverse=True)
        return sorted_doc_score
