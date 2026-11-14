// The app is Italian first. The test suite was written against the English texts, so it runs in English;
// i18n.test.ts and the "in Italian" cases switch language themselves.
import { setLang } from "@/lib/i18n";

setLang("en");
