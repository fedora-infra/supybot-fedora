ns for supybot
==

### TO INSTALL:

1. Move the plugin to a directory where Supybot can access it.
2. @load Fedora
3. If you are not using the main FAS, run
 
         @config plugins.fedora.fas.url [rooturl]
     
4. In a PRIVMSG (/msg) to your bot, say

         @config plugins.fedora.fas.apikey [token]
     
   (This information can only be accessed by bot owners.)
5. @reload Fedora


----------


### Hacking on the plugin and its fedora related libs

Setup your virtual env and fetch submodules

    git submodule init
    git submodule update

Install libs so that you would be able to hack them as well in same virtenv

    pip install -e lib/python-fedora
    pip install -e lib/packagedb-cli
    pip install -e lib/fedmsg
    pip install -e Subpybot

Configure supybot from wizard

    ~/.virtualenvs/supybot-fedora-python2.7/bin/supybot-wizard
    
Use your current dir (supybot-fedora git root dir) as plugins dir
