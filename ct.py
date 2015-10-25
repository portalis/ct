#!/usr/bin/python
# -*- coding: utf-8 -*-


import urllib2
import os
import lxml.html
import re
import io
from datetime import datetime
from datetime import date
from datetime import timedelta
import locale
import itertools
import unidecode
import dateutil
import git
import shutil
import argparse
import unittest
import sys
import textwrap
import threading
import recipe_576515_1

locale.setlocale(locale.LC_ALL, ('fr_FR', 'UTF-8'))
print locale.getlocale()
header = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 5.1; rv:35.0) Gecko/20100101 Firefox/35.0'}
baseUrl = "http://www.legifrance.gouv.fr/"
urlCode = "http://www.legifrance.gouv.fr/affichCode.do?cidTexte=LEGITEXT000006072050&dateTexte="
#handle case when "août" is misspelled

re1Digit = re.compile('^([1-9] )')
reSeparator = re.compile('\W+')
dateUrlFormat = '%Y%m%d'


substitutes = {
               'FEVRIER':'février',
               'DECEMBRE':'décembre',
               'decembre':'décembre',
               'aout':'août',
               'aôut':'août',
               'AOUT':'août',
               '1er':'01',
               '1ER':'01',
} 

def addLeading0(strDate):
    return re1Digit.sub('0\\1', strDate)

def fixDate(uDate):
    strDate = uDate.encode('utf-8','ignore').strip()
    for k in substitutes.keys():
        strDate = strDate.replace(k, substitutes[k])
    return addLeading0(strDate)

def parseDate(uDate):
    try:
        return datetime.strptime(fixDate(uDate), u'%d %B %Y').date()
    except ValueError as e:
        print uDate
        print fixDate(uDate)
        raise e

def addDate(d, str):
    dates.setdefault(d, set()).add(str)

sreDayMonth = u' [0-3]?[0-9][eE]?[rR]?  ?[jJfFmMaAsSoOnNdD][a-zA-Zôûé]{2,9}'
sreYear = u'((19|20)[0-9]{2})'
reDayMonth = re.compile(sreDayMonth)
reYear = re.compile(sreYear)

class DatePicker(dict):
    def __init__(self):
        self.lock = threading.Lock()

    def pickDate(self, histLine):
        dayMonths = reDayMonth.findall(histLine)
        years = reYear.findall(histLine)
        if not dayMonths or not years:
            # histLine has not always a date
            # D513-1
            # http://www.legifrance.com/affichCodeArticle.do?
            #cidTexte=LEGITEXT000006072050&idArticle=LEGIARTI000006644881&
            #dateTexte=20150629
            print("WARNING: No year or day/month in :" + histLine)
        else:
            try:
                d = parseDate(dayMonths[-1] + " " + years[-1][0])
                if u'JORF' not in histLine:
                    d += timedelta(1)
                #histLine should be on one line. Remove ',' for read()
                self.addDate(d, histLine.replace('\n', '').
                               replace('\r', '').
                               replace(',',''))
            except ValueError as e:
                print histLine
                raise e

    def addDate(self, d, histLine):
        self.setdefault(d, set()).add(histLine)

    def getCommitMsg(self, d):
        return unidec(
            d.strftime('%Y-%m-%d ') + u', '.join(self.setdefault(d, set())))

    def getNextDate(self, curDate):
        return next(d for d in sorted(self.keys()) if d > curDate)

    def read(self, f):
        for l in f.readlines():
            d = datetime.strptime(l[:8], '%Y%m%d').date()
            self[d] = set(l[11:].rstrip('\n').split(u', '))

    def write(self, f):
        for k in sorted(self.keys()):
            f.write(unicode(k.strftime('%Y%m%d')) +
                    ' : ' +
                    u', '.join(self[k]) + '\n')

def pathify(path):
    return reSeparator.sub('_', unidec(path))[:255]

def formatArticle(ustrArticle):
    lines = [line.strip() for line in  ustrArticle.split(u'\n')]
    return u"\n\n".join([textwrap.fill(line) for line in lines if line])


reTitle = re.compile('(?<=Article ).*(?= En savoir)')
reTitleSeparator = re.compile(' |\*|\'')
#reTitle = re.compile(
#    'Annexe( Tableau)?|[LRD]\*? ?[0-9]+( BIS)?(\-[0-9]+)*( [AB])? ')
# http://www.legifrance.gouv.fr/affichCode.do;jsessionid=E5D655F41BEB219AB1E1CD5C5038A743.tpdila23v_2?idSectionTA=LEGISCTA000006198573&cidTexte=LEGITEXT000006072050&dateTexte=20150418
# L2323-26-1 A, L2323-26-1 B
class Article:
    def __init__(self, parent, div):
        self.parent = parent
        self.div = div

    def getTitle(self):
        strTitle = self.div.xpath('div[@class="titreArt"]')[0].text_content()
        try:
            return reTitle.search(strTitle).group().strip()
        except AttributeError as e:
            print "no Title in " + strTitle
            print self.parent
            raise e


    def getContent(self):
        return unicode(
            self.div.xpath('div[@class="corpsArt"]')[0].text_content())

    def write(self, path):
        filename = pathify(self.getTitle()) + ".txt"
        fullPath = os.path.join(path, filename)
        with io.open(fullPath, 'w') as f:
             f.write(formatArticle(self.getContent()))
        try:
            os.symlink(fullPath, os.path.join(rootPath, filename))
        except OSError as e:
            print e.strerror
            print filename
            os.remove(os.path.join(rootPath, filename))

    def pickDates(self, dates):
        for anchor in self.div.xpath('div[@class="histoArt"]/descendant::a'):
            dates.pickDate(anchor.text_content())

def getUpSpan(span):
    return next(span.getparent().getparent().getparent().iterchildren())

def getPath(span):
    path = ''
    while span.tag == "span":
        path = os.path.join(pathify(span.text_content()), path)
        span = getUpSpan(span)
    return path

class Toc:
    def __init__(self, url):
        self.url = url
        self.tree = lxml.html.document_fromstring(
            urllib2.urlopen(
                urllib2.Request(url, None, header)).read())

    def getSectionAnchors(self):
        path = '//div[@id="content_left"]/descendant::a'
        return self.tree.xpath(path)

    def getSectionPaths(self):
        return [getPath(a.getparent().getprevious()) for a in
                self.getSectionAnchors()]

class Section:
    def __init__(self, url):
        self.url = url
        self.tree = lxml.html.document_fromstring(
            urllib2.urlopen(
                urllib2.Request(url, None, header)).read())


    def __string__(self):
        return self.url

    def write(self, rootPath):
        path = self.getPath(rootPath)
        if not os.path.isdir(path):
            os.makedirs(path)
        for article in self.getArticles():
            article.write(path)

    def getPath(self, rootPath):
        articlePath = '//div[@id="content_left"]/div[@class="data"]/ul/li'
        path = rootPath
        dir = self.tree.xpath(articlePath)[0]
        while dir is not None:
            path = os.path.join(path, pathify(dir.xpath('a')[0].
                                              text_content()))
            dirs = dir.xpath('ul/li') or [None]
            dir = dirs[0]
        section = pathify(
            self.tree.xpath('//div[@class="titreSection"]'
                          )[0].text_content())
        return os.path.join(path, section)

    def getArticles(self):
        articles = []
        for div in self.tree.xpath('//div[@class="article"]'):
            articles.append(Article(self, div))
        return articles

    def pickDates(self, dates):
        for article in self.getArticles():
            article.pickDates(dates)

    def getNextSection(self):
        anchors = self.tree.xpath('//a[text()="Bloc suivant >>"]')
        if anchors:
            return Section(baseUrl + anchors[0].get('href'))
        else:
            return None

class SectionThread(threading.Thread):
    def __init__(self, section, rootPath, datePicker):
        super(self.__class__, self).__init__()
        self.section = section
        self.rootPath = rootPath
        self.datePicker = datePicker

    def run(self):
        try:
            self.section.write(self.rootPath)
            with self.datePicker.lock as lock:
                self.section.pickDates(self.datePicker)
        except Exception as e :
            print e
            print self.section.url
        sys.stdout.write('.')
        sys.stdout.flush()

def getUrlTree(url):
    return lxml.html.fromstring(
        urllib2.urlopen(
            urllib2.Request(url, None, header)).read())

def emptyRootPath():
    for f in os.listdir(rootPath):
        if f != ".git" and f != "dates.txt" and not f.endswith(".py"):
            if os.path.isdir(os.path.join(rootPath, f)):
                shutil.rmtree(os.path.join(rootPath, f))
            else:
                os.remove(os.path.join(rootPath, f))


#def writeToc(url):
#    tocTree = getUrlTree(url)
#    with io.open(os.path.join(rootPath, "sommaire.txt"), 'w') as f:
#        f.write(tocTree.xpath('//div[@id="content_left"]')[0].text_content())

def writeToc(tocTree):
    with io.open(os.path.join(rootPath, "sommaire.txt"), 'w') as f:
        f.write(tocTree.xpath('//div[@id="content_left"]')[0].text_content())

def commitCode(curDate, datePicker):
    index = repo.index
    index.add(['*'])
    for f in index.diff(None, diff_filter = 'D'):
        index.remove([f.a_blob], workingTree = False)
    message = datePicker.getCommitMsg(curDate)
    index.commit(message)
    print message



def writeSections(section, datePicker, rootPath):
    while section is not None:
        try:
            section.write(rootPath)
            section.pickDates(datePicker)
            sys.stdout.write('.')
            sys.stdout.flush()
            section = section.getNextSection()
        except Exception as e :
            print e
            print section.url
            raise e
    print ("")


def resumeCode(curDate, datePicker, rootPath):
    toc = Toc(urlCode + curDate.strftime('%Y%m%d'))
    sectionPaths = toc.getSectionPaths()
    print "total: ", len(sectionPaths), " sections\n"
    iSection = 0
    while (iSection < len(sectionPaths) and
           os.path.isdir(os.path.join(rootPath, sectionPaths[iSection]))):
        iSection = iSection + 1
        sys.stdout.write('-')
        sys.stdout.flush()
    print iSection
    if iSection < len(sectionPaths):
        print sectionPaths[iSection]
        section = Section(baseUrl +
                          toc.getSectionAnchors()[iSection].get('href'))
        writeSections(section, datePicker, rootPath)
    with io.open(os.path.join(rootPath, "dates.txt"), 'w') as f:
        datePicker.write(f)
    commitCode(curDate, datePicker)

def writeCode(curDate, datePicker, rootPath):
    emptyRootPath()
    tocTree = getUrlTree(urlCode + curDate.strftime('%Y%m%d'))
    writeToc(tocTree)
    urlSection = tocTree.xpath(
        '//div[@id="content_left"]/descendant::a')[0].get('href')
    section = Section(baseUrl + urlSection)
#    threads = []
    writeSections(section, datePicker, rootPath)
#    for thread in threads:
#        thread.join()
    with io.open(os.path.join(rootPath, "dates.txt"), 'w') as f:
        datePicker.write(f)
    commitCode(curDate, datePicker)


# def getCommitMsg(d):
#     return unidec(
#             d.strftime('%Y-%m-%d ') + u', '.join(dates.setdefault(d, set())))
#unidecode writes 'deg' for '°'

def unidec(ustr):
    return unidecode.unidecode(ustr.replace(u'°', u'o'))

def configRepo(repo):
    configWriter = repo.config_writer()
    try:
        configWriter.add_section('user')
    except:
        pass
    configWriter.set('user','name','Portalis')
    configWriter.set('user','email','jem.portalis@free.fr')


testSectionUrl = ("http://www.legifrance.gouv.fr/affichCode.do?" +
    "idSectionTA=LEGISCTA000006178279&cidTexte=LEGITEXT000006072050&" +
    "dateTexte=20150629")
testSectionUrls = [
    "http://www.legifrance.gouv.fr/affichCode.do?" +
    "idSectionTA=LEGISCTA000006198573&cidTexte=LEGITEXT000006072050&" +
    "dateTexte=20150418",
    "http://www.legifrance.gouv.fr//affichCode.do?" +
    "idSectionTA=LEGISCTA000024800129&cidTexte=LEGITEXT000006072050&" +
    "dateTexte=20150418",
    ]
class UnitTests(unittest.TestCase):
    def test_Toc(self):
        toc = Toc(urlCode + "20110811")
        self.assertTrue(toc.tree is not None)
        sectionPaths = toc.getSectionPaths()
        self.assertEqual(2920, len(sectionPaths))
        
        self.assertEqual(
            'Partie_legislative_/Chapitre_preliminaire_Dialogue_social_/',
            sectionPaths[0])
#        self.assertTrue(os.path.isdir(os.path.join(rootPath,
#                                                   toc.getSectionPaths()[0])))
        self.assertEqual(
            'Partie_legislative_/' +
            'Premiere_partie_Les_relations_individuelles_de_travail/' +
            'Livre_Ier_Dispositions_preliminaires/' +
            'Titre_Ier_Champ_d_application_et_calcul_des_seuils_d_effectifs_/' +
            'Chapitre_unique_/',
            sectionPaths[1])
        self.assertEqual(
            'Partie_legislative_/' +
            'Premiere_partie_Les_relations_individuelles_de_travail/' +
            'Livre_Ier_Dispositions_preliminaires/' +
            'Titre_II_Droits_et_libertes_dans_l_entreprise/' +
            'Chapitre_unique_/',
            sectionPaths[2])
        self.assertEqual(
            'Partie_reglementaire_ancienne_Decrets_simples/' +
            'Livre_IX_De_la_formation_professionnelle_continue_' +
            'dans_le_cadre_de_l_education_permanente/' +
            'Titre_VIII_Des_contrats_et_des_periodes_de_professionnalisation/' +
            'Chapitre_Ier_Contrats_d_insertion_en_alternance/' +
            'Section_2_Contrat_d_orientation/',
            sectionPaths[2919])

        toc = Toc(urlCode + "20150417")
        sectionPaths = toc.getSectionPaths()
        self.assertEqual(
            585, len([path for path in sectionPaths
                    if u"Partie_reglementaire_/Quatrieme" in path]))


    def test_reYear(self):
        self.assertEqual(
            reYear.findall("LOI n°2008-67 du 21 janvier 2008")[-1],
            ("2008", "20"))

    def test_reTitle(self):
        articles = Section(testSectionUrl).getArticles()
        titles = [article.getTitle() for article in articles]
        self.assertEqual(["L8252-1","L8252-2","L8252-3","L 8252-4"], titles)

        articles = Section(testSectionUrls[0]).getArticles()
        titles = [article.getTitle() for article in articles]
        self.assertEqual(
            ['L2323-21-1',
             'L2323-22-1',
             'L2323-23-1',
             'L2323-26-1 A',
             'L2323-26-1 B',
             'L2323-21',
             'L2323-22',
             'L2323-23',
             'L2323-24',
             'L2323-25',
             'L2323-26'],
            titles)

        articles = Section(testSectionUrls[1]).getArticles()
        titles = [article.getTitle() for article in articles]
        self.assertEqual(
            [u"Annexe I à l'article R4312-1",
             u"Annexe II à l'article R4312-6"],
            titles)

    def test_section(self):
        self.assertTrue(Section(testSectionUrl).tree is not None)

    def test_pickDateNoDate(self):
        dates = DatePicker()
        dates.pickDate(u"Code du travail - art. D1441-21 (V)")
        self.assertFalse(dates)

    def test_pickDate(self):
        dates = DatePicker()
        dates.pickDate(u"Décret n°2008-244\n du 7 mars 2008 - art. 9 (V)")
        self.assertEqual(1, len(dates.keys()))

    def test_readDates(self):
        f = io.StringIO(u"19721227 : " +
                    u"LOI 72-1150 1972-12-23 ART. 1 JORF 27 DECEMBRE 1972, " +
                        u"LOI 72-1150 1972-12-23 ART. 4 JORF 27 décembre\n" +
                        u"20140829 : " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 2, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 3, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 1, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 6, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 7, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 4, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 5, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 8, " +
                        u"DÉCRET n°2014-985 du 28 août 2014 - art. 9\n")
        dates = DatePicker()
        dates.read(f)
        self.assertEqual(
            2, len(dates.keys()))
    def test_nextSection(self):
        section = Section("http://www.legifrance.gouv.fr/affichCode.do?idSectionTA=LEGISCTA000018534838&cidTexte=LEGITEXT000006072050&dateTexte=20110811")
        section2 = section.getNextSection()

parser = argparse.ArgumentParser()
parser.add_argument('path')
parser.add_argument('times', type = int)
parser.add_argument('--test', action = 'store_true')
parser.add_argument('--resume', action = 'store_true')
args = parser.parse_args()
rootPath = args.path
times = args.times

if args.test:
    unittest.main(argv = [sys.argv[0]])
else:
    recipe_576515_1.listen()
    repo = git.Repo(rootPath)
    configRepo(repo)
    datePicker = DatePicker()
    with io.open(os.path.join(rootPath, "dates.txt"), 'r') as f:
        datePicker.read(f)
    curDate = datetime.strptime(repo.head.commit.message[:10],
                            '%Y-%m-%d').date()
    print curDate
    if not args.resume:
        for i in range(times):
            curDate = datePicker.getNextDate(curDate)
            print curDate
            print datePicker[curDate]
            writeCode(curDate, datePicker, rootPath)
    else:
        curDate = datePicker.getNextDate(curDate)
        print curDate
        print datePicker[curDate]
        resumeCode(curDate, datePicker, rootPath)
