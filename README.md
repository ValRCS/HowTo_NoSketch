# HowTo_NoSketch
How to add corpora to NoSketch engine

---
## NoSketch engine description

https://www.sketchengine.eu/nosketch-engine/

NoSketch Engine is an open source version of Sketch Engine with certain functionality limitations. NoSketch Engine does not contain any corpora, the user must possess adequate technical knowledge of using external tools to prepare corpora for use with NoSketch Engine.

---
## NoSketch at National Library of Latvia

NoSketch Engine is available to researchers and interested public at the following address
https://nosketch.lnb.lv

---
## Steps to add a new corpora to NoSketch

* Collect plaintext and any relevant metadata(title,author,published, et al)
* Prepare XML file - one file combines multiple plaintext documents with relevant metadata
* Perform conversion to .vert file - one token per line with its POS and lemma - we use tool developed by nlp.ailab.lv for Latvian language
```java -Xmx8G  -Dfile.encoding=UTF8 -jar tagger-2.2.1-jar-with-dependencies.jar -vert -keep-tags -output-separators -whitespace-marker -allow-empty-lines < meaningful_name.xml > meaningful_name.vert```
For Latvian tagger-2.2.1-jar-with-dependencies.jar - contact ailab.lv
* Create configuration file - example provided at https://github.com/ValRCS/HowTo_NoSketch/blob/main/sample_config/latvian_early_novels
* [Documentation for Config](https://www.sketchengine.eu/documentation/corpus-configuration-file-all-features/)


### The following steps are for internal use as they  require access to our server - researchers should contact dh@lnb.lv to add their corpus

* copy meaningful_name.vert into /corpora/vert
* **optional** ```mv meaningful_name.vert meaningful_name_datestamp.vert``` and ```ln -s meaningful_name_datestamp.vert meaningful_name.ver```
* copy meaningful_name configuration file into ```/corpora/registry``` - no extension
* cd /corpora/registry 
* compile ```sudo compilecorp --no-sketches --recompile-corpus meaningful_name``` (must match configuration name)
* check that compilation succeeded and multiple files with meaningful_name.some_extension were added to /corpora/data
* edit /var/www/bonito/run.cgi - add meaningful_name to corplist - (use Unicode for non ASCII u'meaningful_name' - this is Python 2.7 )
* restart Apache - ```sudo systemctl restart apache2```
* Check that newly added meaningful_name corpus is available at nosketch.lnb.lv
* Celebrate success/failure with a responsible drink


### Steps to add a subcorpus

* ```cd /corpora/registry```
* if there is no "subcorpora" directory, add it: ```sudo mkdir subcorpora```
* create a text file meaningful_name.txt into /corpora/registry: ```sudo cat subcorpora/meaningful_name.txt```
* add corpus title. E.g.: =Subcorpus title
* in new line, add subcorpus criteria. That can be defined in 2 ways:
  * using text types (they can be found in corpus info or in registry file under STRUCTURE doc) and its value (value also can be regular expression). E.g.:  
doc  
title="The Title"  

  * using CQL query. E.g:  
-CQL-  
[tag="N.\*"] [tag="N.\*"]
* here is example of subcorpus definition file:  
=Subcorpus "Atdzejojumi"  
doc  
title="Atdzejojumi"  <br><br>
=Other files  
doc  
title="[^A].*"  
* to save file press Ctrl (cmd) + d
* within the registry file after NAME "Corpus name" add this line:  
SUBCDEF /corpora/registry/subcorpora/meaningful_name.txt
* compile subcorpus ```sudo compilecorp --no-sketches --recompile-subcorpora meaningful_name ```  <br><br>
For each corpus there should be only 1 subcorpus definition file. Within the definition file there can be many subcorpora defined.

## Instructions for Docker Container

The following instructions are applicable for Docker Container images from: https://github.com/elte-dh/NoSketch-Engine-Docker - currently used by https://korpuss.lnb.lv

### Creating Container

* Installation https://github.com/elte-dh/NoSketch-Engine-Docker?tab=readme-ov-file#tldr

#### Configuring NGINX reverse proxy 

* set up your ssl_certificate and ssl_certificate_key if you have not done already  in sites-enabled default file
* the sole location in your sites-enabled default config would be
  `
  location / {
		proxy_pass http://127.0.0.1:10070;
	}
`

### Adding Corpora to Docker Container

Docker container uses the following structure for corpora

* ${your_install_path}/corpora - all corpora related files
* ${your_install_path}/corpora/registry - all registry files for individual corpora in same folder, so you would have my_corpus_name registry file here
* ${your_install_path}/corpora/my_corpus_name - holds both vert and compiled files for individual corpus
* ${your_install_path}/corpora/my_corpus_name/vertical - would hold my_corpus_name.vert file
* ${your_install_path}/corpora/my_corpus_name/indexed - will hold compiled files, indexed folder will be created in compilation process

  #### Compiling

  * Copy my_corpus_name.vert to ${your_install_path}/corpora/my_corpus_name/vertical
  * Copy my_corpus (the registry file) to ${your_install_path}/corpora/registry

Registry file head (first two rows) should look like this:
`PATH  '/corpora/my_corpus_name/indexed'
VERTICAL '/corpora/my_corpus_name/vertical/my_corpus_name.vert'
`

  * Compile all corpora listed in corpora/registry directory using the docker image: `make compile`
  * Compile individual corpora one at a time - `docker exec noske compilecorp --no-ske --recompile-corpus my_corpus_name`
    Note: This assumes you default naming for the container - noske.
    Note2: make execute command as of 16.04.2024 does not work for commands with arguments 
    i.e. - `make compile` works but single corpus compilation recommended `make execute CMD="compilecorp --no-ske --recompile-corpus CORPUS_REGISTRY_FILE` does not work due the the way Docker processes arguments in container's shell
    There are workarounds for this see: https://stackoverflow.com/questions/32727594/how-to-pass-arguments-to-shell-script-through-docker-run
