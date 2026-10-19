# chinese / cantonese g2p dictionaries

openutau romanizes hanzi with **csharp-pinyin 1.0.0** (nuget package `csharp-pinyin`, a
dependency of OpenUtau.Core, https://github.com/wolfgitpr/csharp-pinyin, Apache-2.0, © wolfgitpr).
the dictionaries are embedded resources of its `Pinyin.dll`. they were extracted from
`~/.nuget/packages/csharp-pinyin/1.0.0/lib/net6.0/Pinyin.dll` (identical to the copy in
`ref/harness/bin/out/Pinyin.dll`) with `ilspycmd -p`, byte for byte:

| file here | embedded resource |
| --- | --- |
| `mandarin/phrases_map.txt` | `Pinyin.dict.mandarin.phrases_map.txt` |
| `mandarin/phrases_dict.txt` | `Pinyin.dict.mandarin.phrases_dict.txt` |
| `mandarin/user_dict.txt` | `Pinyin.dict.mandarin.user_dict.txt` |
| `mandarin/word.txt` | `Pinyin.dict.mandarin.word.txt` |
| `mandarin/trans_word.txt` | `Pinyin.dict.mandarin.trans_word.txt` |
| `mandarin/License.txt` | `Pinyin.dict.mandarin.License.txt` |
| `cantonese/phrases_map.txt` | `Pinyin.dict.cantonese.phrases_map.txt` |
| `cantonese/phrases_dict.txt` | `Pinyin.dict.cantonese.phrases_dict.txt` |
| `cantonese/user_dict.txt` | `Pinyin.dict.cantonese.user_dict.txt` |
| `cantonese/word.txt` | `Pinyin.dict.cantonese.word.txt` |
| `cantonese/trans_word.txt` | `Pinyin.dict.cantonese.trans_word.txt` |
| `cantonese/License.txt` | `Pinyin.dict.cantonese.License.txt` |

the library code is Apache-2.0; the mandarin data derives from CC-CEDICT and the cantonese data
from CC-Canto (both CC BY-SA 3.0, see the License.txt files). `../../_pinyin.py` is the python
port of the library code that reads them.
