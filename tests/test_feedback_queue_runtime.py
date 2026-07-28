import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FeedbackQueueRuntimeTest(unittest.TestCase):
    def run_scenario(self, scenario):
        html = (ROOT / "template.html").read_text(encoding="utf-8")
        section = html[
            html.index("const feedbackQueueKey="):
            html.index("/* ========== 发音引擎")]
        prelude = r"""
const storage = new Map();
const localStorage = {
  getItem: key => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
};
const ARTICLE = {date:'2026-07-28'};
let progressState = {
  difficultyFeedback:null, completed:false, quizFirstScore:null, quizTotal:0,
  wordActionCount:0, phraseActionCount:0, learningActionKeys:[],
};
function saveProgress(patch){ progressState={...progressState,...patch}; return progressState; }
const statusNode = {textContent:''};
const document = {
  getElementById: id => statusNode,
  querySelectorAll: () => [],
};
let accessKeyValue='saved-key';
function storedAccessKey(){ return accessKeyValue; }
const cloudOn=true;
function addEventListener(){}
let requestHandler=async()=>({ok:true,json:async()=>({ok:true,profile:{trend:'stable'}})});
async function protectedFetch(payload,options){ return requestHandler(payload,options); }
"""
        script = prelude + section + "\n(async()=>{" + scenario + r"""
})().catch(error=>{ console.error(error.stack||error); process.exitCode=1; });
"""
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_drains_prior_dates_and_does_not_create_blank_current_event(self):
        self.run_scenario(r"""
const sent=[];
requestHandler=async payload=>{
  sent.push(payload);
  return {ok:true,json:async()=>({ok:true,profile:{trend:'stable'}})};
};
writeFeedbackQueue({
  '2026-07-27':{op:'feedback_put',article_date:'2026-07-27',difficulty:'hard',
    completed:true,quiz_first_score:2,quiz_total:4,word_action_count:8,phrase_action_count:1},
  '2026-07-28':{op:'feedback_put',article_date:'2026-07-28',difficulty:'balanced',
    completed:true,quiz_first_score:3,quiz_total:4,word_action_count:6,phrase_action_count:1},
});
await syncLearningFeedback(false);
if(sent.map(item=>item.article_date).join(',')!=='2026-07-27,2026-07-28')
  throw new Error('pending dates were not drained in order');
if(Object.keys(readFeedbackQueue()).length)throw new Error('queue was not emptied');
await syncLearningFeedback(false);
if(sent.length!==2)throw new Error('empty retry synthesized a new observation');
""")

    def test_newer_same_date_payload_survives_older_in_flight_response(self):
        self.run_scenario(r"""
let releaseFirst;
const firstResponse=new Promise(resolve=>{releaseFirst=resolve;});
const sent=[];
requestHandler=async payload=>{
  sent.push(JSON.parse(JSON.stringify(payload)));
  if(sent.length===1)return firstResponse;
  return {ok:true,json:async()=>({ok:true,profile:{trend:'easier'}})};
};
queueLearningFeedback({op:'feedback_put',article_date:'2026-07-28',difficulty:'easy',
  completed:true,quiz_first_score:4,quiz_total:4,word_action_count:2,phrase_action_count:0});
const running=syncLearningFeedback(false);
await new Promise(resolve=>setTimeout(resolve,0));
queueLearningFeedback({op:'feedback_put',article_date:'2026-07-28',difficulty:'hard',
  completed:true,quiz_first_score:4,quiz_total:4,word_action_count:2,phrase_action_count:0});
releaseFirst({ok:true,json:async()=>({ok:true,profile:{trend:'harder'}})});
await running;
if(sent.length!==2)throw new Error('newer payload was not retried');
if(sent[1].difficulty!=='hard')throw new Error('newer difficulty was lost');
if(Object.keys(readFeedbackQueue()).length)throw new Error('latest payload remains queued');
""")


if __name__ == "__main__":
    unittest.main()
