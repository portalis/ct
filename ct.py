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



locale.setlocale(locale.LC_ALL, ('fr_FR', 'UTF-8'))
print locale.getlocale()
header = {
    'User-Agent':
    'Mozilla/5.0 (Windows NT 5.1; rv:35.0) Gecko/20100101 Firefox/35.0'}
baseUrl = "http://www.legifrance.gouv.fr/"
urlCode = "http://www.legifrance.gouv.fr/affichCode.do"+ \
          "?cidTexte=LEGITEXT000006072050&dateTexte="
#handle case when "août" is misspelled

re1Digit = re.compile('^([1-9] )')
reSeparator = re.compile('\W+')
dateUrlFormat = '%Y%m%d'
#firstDate = date(1978, 1, 20)


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
reDate = re.compile(sreDayMonth + u' ' + sreYear)
reDayMonth = re.compile(sreDayMonth)
reYear = re.compile(sreYear)

class DatePicker(dict):
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

def pickDates(article):
    for anchor in article.xpath('div[@class="histoArt"]/descendant::a'):
        histLine = anchor.text_content()
        try:
            d = parseDate(
                reDayMonth.findall(histLine)[-1] +
                ' ' + reYear.findall(histLine)[-1])
            if u'JORF' not in histLine:
                d += timedelta(1)
            #histLine should be on one line. Remove ',' for readDates
            addDate(d, histLine.replace('\n', '').
                               replace('\r', '').
                               replace(',',''))
        except ValueError as e:
            print histLine
            raise e
        except IndexError as e:
            print str(e)
            print histLine
            #raise e #D513-1 2007-11-01

def writeArticle(path, article):
    strTitle = article.xpath('div[@class="titreArt"]')[0].text_content()
    try:
        title = reTitle.search(strTitle).group().strip()
    except AttributeError as e:
        print "no Title in " + strTitle
        print path
        raise e
    contentArticle = unicode(
        article.xpath('div[@class="corpsArt"]')[0].text_content())
    with io.open(os.path.join(path, pathify(title) + ".txt"), 'w') as f:
        f.write(contentArticle)

def pathify(path):
    return reSeparator.sub('_', unidec(path))[:255]

def getPath(treeArticle):
    path = rootPath
    dir = treeArticle.xpath(
        '//div[@id="content_left"]/div[@class="data"]/ul/li')[0]
    while dir is not None:
        path = os.path.join(path, pathify(dir.xpath('a')[0].text_content()))
        dirs = dir.xpath('ul/li') or [None]
        dir = dirs[0]
    section = pathify(
        treeArticle.xpath('//div[@class="titreSection"]')[0].text_content())
    return os.path.join(path, section)

def writeSection(treeSection):
    path = getPath(treeSection)
    if not os.path.isdir(path):
        os.makedirs(path)
    for article in treeSection.xpath('//div[@class="article"]'):
        writeArticle(path, article)
        pickDates(article)

def formatArticle(ustrArticle):
    lines = [line.strip() for line in  ustrArticle.split(u'\n')]
    return u"\n\n".join([textwrap.fill(line) for line in lines if line])

reTitle = re.compile('Annexe( Tableau)?|[LRD]\*? ?[0-9]+( BIS)?(\-[0-9]+)* ')

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
        with io.open(os.path.join(path, pathify(self.getTitle()) + ".txt"),
                     'w') as f:
             f.write(formatArticle(self.getContent()))

    def pickDates(self, dates):
        for anchor in self.div.xpath('div[@class="histoArt"]/descendant::a'):
            dates.pickDate(anchor.text_content())

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

def getUrlTree(url):
    return lxml.html.fromstring(
        urllib2.urlopen(
            urllib2.Request(url, None, header)).read())

def emptyRootPath():
    for f in os.listdir(rootPath):
        if f != ".git" and f != "dates.txt" and f != "ct.py":
            if os.path.isdir(os.path.join(rootPath, f)):
                shutil.rmtree(os.path.join(rootPath, f))
            else:
                os.remove(os.path.join(rootPath, f))

def writeDates():
    with io.open(os.path.join(rootPath, "dates.txt"), 'w') as f:
        for k in sorted(dates.keys()):
            f.write(unicode(k.strftime('%Y%m%d')) +
                    ' : ' +
                    u', '.join(dates[k]) + '\n')

def readDates():
    ldates = {}
    with io.open(os.path.join(rootPath, "dates.txt"), 'r') as f:
        for l in f.readlines():
            d = datetime.strptime(l[:8], '%Y%m%d').date()
            ldates[d] = set(l[11:].rstrip('\n').split(u', '))
    return ldates

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

def writeCode(curDate, datePicker, rootPath):
    emptyRootPath()
    tocTree = getUrlTree(urlCode + curDate.strftime('%Y%m%d'))
    writeToc(tocTree)
    urlSection = tocTree.xpath(
        '//div[@id="content_left"]/descendant::a')[0].get('href')
    section = Section(baseUrl + urlSection)
    while section is not None:
        section.write(rootPath)
        section.pickDates(datePicker)
        section = section.getNextSection()
        sys.stdout.write('.')
        sys.stdout.flush()
    print("")
    with io.open(os.path.join(rootPath, "dates.txt"), 'w') as f:
        datePicker.write(f)
    commitCode(curDate, datePicker)


def getCommitMsg(d):
    return unidec(
            d.strftime('%Y-%m-%d ') + u', '.join(dates.setdefault(d, set())))
#unidecode writes 'deg' for '°'

def unidec(ustr):
    return unidecode.unidecode(ustr.replace(u'°', u'o'))

# def nextDate(curDate):
#     return next(d for d in sorted(dates.keys()) if d > curDate)

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
class UnitTests(unittest.TestCase):
    def test_reYear(self):
        self.assertEqual(
            reYear.findall("LOI n°2008-67 du 21 janvier 2008")[-1],
            ("2008", "20"))

    def test_reTitle(self):
        title = Section(testSectionUrl).getArticles()[0].getTitle()
        self.assertEqual("L8252-1", title)
        title = Section(testSectionUrl).getArticles()[1].getTitle()
        self.assertEqual("L8252-2", title)
        title = Section(testSectionUrl).getArticles()[2].getTitle()
        self.assertEqual("L8252-3", title)
        title = Section(testSectionUrl).getArticles()[3].getTitle()
        self.assertEqual("L 8252-4", title)

    def test_section(self):
        self.assertTrue(Section(testSectionUrl).tree)

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


parser = argparse.ArgumentParser()
parser.add_argument('path')
parser.add_argument('times', type = int)
parser.add_argument('--recover', action = 'store_true')
parser.add_argument('--test', action = 'store_true')
args = parser.parse_args()
rootPath = args.path
times = args.times

if args.test:
    unittest.main(argv = [sys.argv[0]])
else:
    repo = git.Repo(rootPath)
    configRepo(repo)
    datePicker = DatePicker()
    with io.open(os.path.join(rootPath, "dates.txt"), 'r') as f:
         datePicker.read(f)
    if not args.recover:
        curDate = datetime.strptime(repo.head.commit.message[:10],
                                '%Y-%m-%d').date()
        print curDate
        for i in range(times):
            curDate = datePicker.getNextDate(curDate)
            print curDate
            print datePicker[curDate]
            writeCode(curDate, datePicker, rootPath)
    else:
        recoverBranch = repo.create_head(
            'recover_' +
            datetime.utcnow().strftime('%Y-%m-%dT%H%M%s'))
        commitDates = {}
        for commit in repo.iter_commits('master'):
            commitDates[
                datetime.strptime(commit.message[:10], '%Y-%m-%d').date()
            ] = commit
            curDate = next(
                d for d in sorted(dates.keys()) if d not in commitDates)
            print curDate
            prevCommitDate = next(
                d for d in sorted(
                    commitDates.keys(), reverse = True)
                if d < curDates)
            print commitDates[prevCommitDate].message
            recoverBranch.set_commit(commitDates[prevCommitDate])
            recoverBranch.checkout()
            writeCode(curDate)
