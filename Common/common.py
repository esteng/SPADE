import time
from datetime import datetime
import os
import sys

sys.path.insert(0, '/mnt/e/Dev/Polyglot/PolyglotDB')
import re
import yaml
import csv
import platform
import polyglotdb.io as pgio

from polyglotdb import CorpusContext
from polyglotdb.io.enrichment import enrich_speakers_from_csv, enrich_lexicon_from_csv
from polyglotdb.acoustics.formants.refined import analyze_formant_points_refinement

# =============== CONFIGURATION ===============

duration_threshold = 0.05
nIterations = 1

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sibilant_script_path = os.path.join(base_dir, 'Common', 'sibilant_jane_optimized.praat')

# =============================================
now = datetime.now()
date = '{}-{}-{}'.format(now.year, now.month, now.day)


def save_performance_benchmark(config, task, time_taken):
    benchmark_folder = os.path.join(base_dir, 'benchmarks')
    os.makedirs(benchmark_folder, exist_ok=True)
    benchmark_file = os.path.join(benchmark_folder, 'benchmarks.csv')
    if not os.path.exists(benchmark_file):
        with open(benchmark_file, 'w', encoding='utf8') as f:
            writer = csv.writer(f, delimiter=',')
            writer.writerow(['Computer', 'Corpus', 'Date', 'Corpus_size', 'Task', 'Time'])
    with open(benchmark_file, 'a', encoding='utf8') as f:
        writer = csv.writer(f, delimiter=',')
        writer.writerow([platform.node(), config.corpus_name, date, get_size_of_corpus(config), task, time_taken])


def load_config(corpus_name):
    path = os.path.join(base_dir, corpus_name, '{}.yaml'.format(corpus_name))
    if not os.path.exists(path):
        print('The config file for the specified corpus does not exist ({}).'.format(path))
        sys.exit(1)
    expected_keys = ['corpus_directory', 'input_format', 'dialect_code', 'unisyn_spade_directory',
                     'speaker_enrichment_file',
                     'speakers', 'vowel_inventory', 'stressed_vowels', 'sibilant_segments']
    with open(path, 'r', encoding='utf8') as f:
        conf = yaml.load(f)
    missing_keys = []
    for k in expected_keys:
        if k not in conf:
            missing_keys.append(k)
    if missing_keys:
        print('The following keys were missing from {}: {}'.format(path, ', '.join(missing_keys)))
        sys.exit(1)
    return conf


def call_back(*args):
    args = [x for x in args if isinstance(x, str)]
    if args:
        print(' '.join(args))


def reset(config):
    with CorpusContext(config) as c:
        print('Resetting the corpus.')
        c.reset()


def loading(config, corpus_dir, textgrid_format):
    with CorpusContext(config) as c:
        exists = c.exists()
    if exists:
        print('Corpus already loaded, skipping import.')
        return
    if not os.path.exists(corpus_dir):
        print('The path {} does not exist.'.format(corpus_dir))
        sys.exit(1)
    with CorpusContext(config) as c:
        print('loading')

        if textgrid_format == "buckeye":
            parser = pgio.inspect_buckeye(corpus_dir)
        elif textgrid_format == "csv":
            parser = pgio.inspect_buckeye(corpus_dir)
        elif textgrid_format.lower() == "fave":
            parser = pgio.inspect_fave(corpus_dir)
        elif textgrid_format == "ilg":
            parser = pgio.inspect_ilg(corpus_dir)
        elif textgrid_format == "labbcat":
            parser = pgio.inspect_labbcat(corpus_dir)
        elif textgrid_format == "partitur":
            parser = pgio.inspect_partitur(corpus_dir)
        elif textgrid_format == "timit":
            parser = pgio.inspect_timit(corpus_dir)
        else:
            parser = pgio.inspect_mfa(corpus_dir)
        parser.call_back = call_back
        beg = time.time()
        c.load(parser, corpus_dir)
        end = time.time()
        time_taken = end - beg
        print('Loading took: {}'.format(time_taken))
    save_performance_benchmark(config, 'import', time_taken)


def basic_enrichment(config, syllabics, pauses):
    with CorpusContext(config) as g:
        if not 'utterance' in g.annotation_types:
            print('encoding utterances')
            begin = time.time()
            g.encode_pauses(pauses)
            # g.encode_pauses('^[<{].*$', call_back = call_back)
            g.encode_utterances(min_pause_length=0.15)  # , call_back = call_back)
            # g.encode_utterances(min_pause_length = 0.5, call_back = call_back)
            time_taken = time.time() - begin
            print('Utterance enrichment took: {}'.format(time_taken))
            save_performance_benchmark(config, 'utterance_encoding', time_taken)

        if syllabics and 'syllable' not in g.annotation_types:
            print('encoding syllables')
            begin = time.time()
            g.encode_syllabic_segments(syllabics)
            g.encode_syllables('maxonset')
            time_taken = time.time() - begin
            print('Syllable enrichment took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'syllable_encoding', time_taken)

        print('enriching utterances')
        if syllabics and not g.hierarchy.has_token_property('utterance', 'speech_rate'):
            begin = time.time()
            g.encode_rate('utterance', 'syllable', 'speech_rate')
            time_taken = time.time() - begin
            print('Speech rate encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'speech_rate_encoding', time_taken)

        if not g.hierarchy.has_token_property('utterance', 'num_words'):
            begin = time.time()
            g.encode_count('utterance', 'word', 'num_words')
            time_taken = time.time() - begin
            print('Word count encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'num_words_encoding', time_taken)

        if syllabics and not g.hierarchy.has_token_property('utterance', 'num_syllables'):
            begin = time.time()
            g.encode_count('utterance', 'syllable', 'num_syllables')
            time_taken = time.time() - begin
            print('Syllable count encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'num_syllables_encoding', time_taken)

        if syllabics and not g.hierarchy.has_token_property('syllable', 'position_in_word'):
            print('enriching syllables')
            begin = time.time()
            g.encode_position('word', 'syllable', 'position_in_word')
            time_taken = time.time() - begin
            print('Syllable position encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'position_in_word_encoding', time_taken)

        if syllabics and not g.hierarchy.has_token_property('syllable', 'num_phones'):
            begin = time.time()
            g.encode_count('syllable', 'phone', 'num_phones')
            time_taken = time.time() - begin
            print('Phone count encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'num_phones_encoding', time_taken)

        # print('enriching words')
        # if not g.hierarchy.has_token_property('word', 'position_in_utterance'):
        #    begin = time.time()
        #    g.encode_position('utterance', 'word', 'position_in_utterance')
        #    print('Utterance position encoding took: {}'.format(time.time() - begin))

        if syllabics and not g.hierarchy.has_token_property('word', 'num_syllables'):
            begin = time.time()
            g.encode_count('word', 'syllable', 'num_syllables')
            time_taken = time.time() - begin
            print('Syllable count encoding took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'num_syllables_encoding', time_taken)

        print('enriching syllables')
        if syllabics and g.hierarchy.has_type_property('word', 'stresspattern') and not g.hierarchy.has_token_property('syllable',
                                                                                                         'stress'):
            begin = time.time()
            g.encode_stress_from_word_property('stresspattern')
            time_taken = time.time() - begin
            print("encoded stress")
            save_performance_benchmark(config, 'stress_encoding_from_pattern', time_taken)
        elif syllabics and re.search(r"\d", syllabics[0]) and not g.hierarchy.has_type_property('syllable',
                                                                                                'stress'):  # If stress is included in the vowels
            begin = time.time()
            g.encode_stress_to_syllables("[0-9]", clean_phone_label=False)
            time_taken = time.time() - begin
            print("encoded stress")
            save_performance_benchmark(config, 'stress_encoding', time_taken)


def lexicon_enrichment(config, unisyn_spade_directory, dialect_code):
    enrichment_dir = os.path.join(unisyn_spade_directory, 'enrichment_files')
    if not os.path.exists(enrichment_dir):
        print('Could not find enrichment_files directory from {}, skipping lexical enrichment.'.format(
            unisyn_spade_directory))
        return
    with CorpusContext(config) as g:

        for lf in os.listdir(enrichment_dir):
            path = os.path.join(enrichment_dir, lf)
            if lf == 'rule_applications.csv':
                if g.hierarchy.has_type_property('word', 'UnisynPrimStressedVowel1'.lower()):
                    print('Dialect independent enrichment already loaded, skipping.')
                    continue
            elif lf.startswith(dialect_code):
                if g.hierarchy.has_type_property('word', 'UnisynPrimStressedVowel2_{}'.format(
                        dialect_code).lower()):
                    print('Dialect specific enrichment already loaded, skipping.')
                    continue
            else:
                continue
            begin = time.time()
            enrich_lexicon_from_csv(g, path)
            time_taken = time.time() - begin
            print('Lexicon enrichment took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'lexicon_enrichment', time_taken)


def speaker_enrichment(config, speaker_file):
    if not os.path.exists(speaker_file):
        print('Could not find {}, skipping speaker enrichment.'.format(speaker_file))
        return
    with CorpusContext(config) as g:
        if not g.hierarchy.has_speaker_property('gender'):
            begin = time.time()
            enrich_speakers_from_csv(g, speaker_file)
            time_taken = time.time() - begin
            print('Speaker enrichment took: {}'.format(time.time() - begin))
            save_performance_benchmark(config, 'speaker_enrichment', time_taken)
        else:
            print('Speaker enrichment already done, skipping.')


def sibilant_acoustic_analysis(config, sibilant_segments):
    # Encode sibilant class and analyze sibilants using the praat script
    with CorpusContext(config) as c:
        if c.hierarchy.has_token_property('phone', 'cog'):
            print('Sibilant acoustics already analyzed, skipping.')
            return
        print('Beginning sibilant analysis')
        beg = time.time()
        c.encode_class(sibilant_segments, 'sibilant')
        time_taken = time.time() - beg
        save_performance_benchmark(config, 'sibilant_encoding', time_taken)
        print('sibilants encoded')

        # analyze all sibilants using the script found at script_path
        beg = time.time()
        c.analyze_script('sibilant', sibilant_script_path, duration_threshold=0.01)
        end = time.time()
        time_taken = time.time() - beg
        print('Sibilant analysis took: {}'.format(end - beg))
        save_performance_benchmark(config, 'sibilant_acoustic_analysis', time_taken)


def formant_acoustic_analysis(config, vowels):
    with CorpusContext(config) as c:
        if c.hierarchy.has_token_property('phone', 'F1'):
            print('Formant acoustics already analyzed, skipping.')
            return
        print('Beginning formant analysis')
        beg = time.time()
        metadata = analyze_formant_points_refinement(c, vowels, duration_threshold=duration_threshold,
                                                     num_iterations=nIterations)
        end = time.time()
        time_taken = time.time() - beg
        print('Analyzing formants took: {}'.format(end - beg))
        save_performance_benchmark(config, 'formant_acoustic_analysis', time_taken)


def formant_export(config, corpus_name, dialect_code, speakers, vowels):  # Gets information into a csv

    csv_path = os.path.join(base_dir, corpus_name, '{}_formants.csv'.format(corpus_name))
    # Unisyn columns
    other_vowel_codes = ['unisynPrimStressedVowel2_{}'.format(dialect_code),
                         'UnisynPrimStressedVowel3_{}'.format(dialect_code),
                         'UnisynPrimStressedVowel3_XSAMPA',
                         'AnyRuleApplied_{}'.format(dialect_code)]

    with CorpusContext(config) as c:
        print('Beginning formant export')
        beg = time.time()
        q = c.query_graph(c.phone)
        if speakers:
            q = q.filter(c.phone.speaker.name.in_(speakers))
        q = q.filter(c.phone.label.in_(vowels))

        q = q.columns(c.phone.speaker.name.column_name('speaker'), c.phone.discourse.name.column_name('discourse'),
                      c.phone.id.column_name('phone_id'), c.phone.label.column_name('phone_label'),
                      c.phone.begin.column_name('begin'), c.phone.end.column_name('end'),
                      c.phone.syllable.stress.column_name('syllable_stress'),
                      c.phone.syllable.word.stresspattern.column_name('word_stress_pattern'),
                      c.phone.syllable.position_in_word.column_name('syllable_position_in_word'),
                      c.phone.duration.column_name('duration'),
                      c.phone.following.label.column_name('following_phone'),
                      c.phone.previous.label.column_name('previous_phone'), c.phone.word.label.column_name('word'),
                      c.phone.F1.column_name('F1'), c.phone.F2.column_name('F2'), c.phone.F3.column_name('F3'),
                      c.phone.B1.column_name('B1'), c.phone.B2.column_name('B2'), c.phone.B3.column_name('B3'))
        if c.hierarchy.has_type_property('word', 'UnisynPrimStressedVowel1'.lower()):
            q = q.columns(c.phone.word.unisynprimstressedvowel1.column_name('UnisynPrimStressedVowel1'))
        for v in other_vowel_codes:
            if c.hierarchy.has_type_property('word', v.lower()):
                q = q.columns(getattr(c.phone.word, v.lower()).column_name(v))
        for sp, _ in c.hierarchy.speaker_properties:
            if sp == 'name':
                continue
            q = q.columns(getattr(c.phone.speaker, sp).column_name(sp))
        q.to_csv(csv_path)
        end = time.time()
        time_taken = time.time() - beg
        print('Query took: {}'.format(end - beg))
        print("Results for query written to " + csv_path)
        save_performance_benchmark(config, 'formant_export', time_taken)


def sibilant_export(config, corpus_name, dialect_code, speakers):
    csv_path = os.path.join(base_dir, corpus_name, '{}_sibilants.csv'.format(corpus_name))
    with CorpusContext(config) as c:
        # export to CSV all the measures taken by the script, along with a variety of data about each phone
        print("Beginning sibilant export")
        beg = time.time()
        q = c.query_graph(c.phone).filter(c.phone.subset == 'sibilant')
        #q = q.filter(c.phone.begin == c.phone.syllable.word.begin)
        if speakers:
            q = q.filter(c.phone.speaker.name.in_(speakers))
        # qr = c.query_graph(c.phone).filter(c.phone.subset == 'sibilant')
        # this exports data for all sibilants
        qr = q.columns(c.phone.speaker.name.column_name('speaker'),
                        c.phone.discourse.name.column_name('discourse'),
                        c.phone.id.column_name('phone_id'), c.phone.label.column_name('phone_label'),
                        c.phone.begin.column_name('begin'), c.phone.end.column_name('end'),
                        c.phone.duration.column_name('duration'),
                       #c.phone.syllable.position_in_word.column_name('syllable_position_in_word'),
                        c.phone.following.label.column_name('following_phone'),
                        c.phone.previous.label.column_name('previous_phone'),
                        c.phone.syllable.word.label.column_name('word'),
                        c.phone.syllable.stress.column_name('syllable_stress'),
                        c.phone.syllable.phone.filter_by_subset('onset').label.column_name('onset'),
                        c.phone.syllable.phone.filter_by_subset('nucleus').label.column_name('nucleus'),
                        c.phone.syllable.phone.filter_by_subset('coda').label.column_name('coda'),
                        c.phone.cog.column_name('cog'), c.phone.peak.column_name('peak'),
                        c.phone.slope.column_name('slope'), c.phone.spread.column_name('spread'))
        for sp, _ in c.hierarchy.speaker_properties:
            if sp == 'name':
                continue
            q = q.columns(getattr(c.phone.speaker, sp).column_name(sp))
        qr.to_csv(csv_path)
        end = time.time()
        time_taken = time.time() - beg
        print('Query took: {}'.format(end - beg))
        print("Results for query written to " + csv_path)
        save_performance_benchmark(config, 'sibilant_export', time_taken)


def get_size_of_corpus(config):
    from polyglotdb.query.base.func import Sum
    with CorpusContext(config) as c:
        c.config.query_behavior = 'other'
        if 'utterance' not in c.annotation_types:
            q = c.query_graph(c.word).columns(Sum(c.word.duration).column_name('result'))
        else:
            q = c.query_graph(c.utterance).columns(Sum(c.utterance.duration).column_name('result'))
        results = q.all()
    return results[0]['result']


def basic_queries(config):
    from polyglotdb.query.base.func import Sum
    with CorpusContext(config) as c:
        print(c.hierarchy)
        print('beginning basic queries')
        beg = time.time()
        q = c.query_lexicon(c.lexicon_phone).columns(c.lexicon_phone.label.column_name('label'))
        results = q.all()
        print('The phone inventory is:', ', '.join(sorted(x['label'] for x in results)))
        for r in results:
            total_count = c.query_graph(c.phone).filter(c.phone.label == r['label']).count()
            duration_threshold_count = c.query_graph(c.phone).filter(c.phone.label == r['label']).filter(
                c.phone.duration >= duration_threshold).count()
            qr = c.query_graph(c.phone).filter(c.phone.label == r['label']).limit(1)
            qr = qr.columns(c.phone.word.label.column_name('word'),
                            c.phone.word.transcription.column_name('transcription'))
            res = qr.all()
            if len(res) == 0:
                print('An example for {} was not found.'.format(r['label']))
            else:
                res = res[0]
                print('An example for {} (of {}, {} above {}) is the word "{}" with the transcription [{}]'.format(
                    r['label'], total_count, duration_threshold_count, duration_threshold, res['word'],
                    res['transcription']))

        q = c.query_speakers().columns(c.speaker.name.column_name('name'))
        results = q.all()
        print('The speakers in the corpus are:', ', '.join(sorted(x['name'] for x in results)))
        c.config.query_behavior = 'other'
        q = c.query_graph(c.utterance).columns(Sum(c.utterance.duration).column_name('result'))
        results = q.all()
        q = c.query_graph(c.word).columns(Sum(c.word.duration).column_name('result'))
        word_results = q.all()
        print('The total length of speech in the corpus is: {} seconds (utterances) {} seconds (words'.format(
            results[0]['result'], word_results[0]['result']))
        time_taken = time.time() - beg
        save_performance_benchmark(config, 'basic_query', time_taken)
