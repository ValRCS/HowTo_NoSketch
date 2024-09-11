# Creating Plaintext

## Understanding what you have

First of all, you need to understand what you have. You end goal here should be a corpus in a format that is readable by the NoSketch Engine. 

### NO Sketch Engine vert format
The NoSketch Engine uses a vertical file format. A vertical file is a text file where each line represents a token (word, punctuation, etc.) and each sentence is separated by an empty line. The first line of the file should contain the number of tokens in the file. The second line should contain the number of sentences in the file. The rest of the file should contain the tokens. Here is an example of a vertical file:

```plaintext
<doc title="Patrioti" isPartOf="Rīga" creator="Deglavs, Augusts, 1862–1922" dateIssued="1951" publisher="Latvijas Valsts Izdevniecība" firstPublished="1912" firstEdition="1912" copyright="Nav aizsargāts ar autortiesībām" uri="http://dom.lndb.lv/data/obj/103063" normalization="" ocrCorrection="Jā" verified="07.04.2022, Name,LastName" pubPlace="Rīga">
<p>
<s>
<g />
PATRIOTI	ncmpn1	patriots
</s>
</p>
<p>
<s>
<g />
DIVĀS	mcsfpl	divi
DAĻĀS	ncfpl4	daļa

</s>
</p>
</doc>
```

### Finding your existing file structure

It might be a good idea to first have a manual look or a programmatic analysis of your existing files. You might have a collection of text files, a database, or some other format. You need to understand how you can convert your existing files into the NoSketch Engine vert format. 

Common formats that you might have are:
- Text files - .txt extension would be common - this would be a simple format to convert
- CSV files - .csv extension would be common - this would be a simple format to convert
- JSON files - .json extension would be common - this would be slightly more complex to convert
- alto xml files from OCR software - .xml extension would be common - this would be a more complex format to convert
- hocr files from OCR software - .hocr extension would be common - this would be a more complex format to convert
- some generic XML files - .xml extension would be common - this would be a more complex format to convert
- PDF files - .pdf extension would be common - this would be a more complex format to convert
- DOCX files - .docx extension would be common - this would be a more complex format to convert
- HTML files - .html extension would be common - this would be a more complex format to convert
- JPG, PNG, TIFF, etc. image files - this would be a more complex format to convert since you need to use OCR software to convert the images to text