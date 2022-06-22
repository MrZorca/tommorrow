from sklearn.metrics.pairwise import cosine_similarity
import joblib
import pandas as pd
from flask import Flask, request, render_template
from turbo_flask import Turbo
import nltk
from nltk.corpus import stopwords
from transformers import pipeline
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer, util

nltk.download('stopwords')
#Create Flask app
app = Flask(__name__, static_folder="templates/static/")
app.config["TEMPLATES_AUTO_RELOAD"] = True
turbo = Turbo(app)

tokenizer = nltk.RegexpTokenizer(r"\w+")

#Access the video-ad dataset (pre-analysed video/label detections)
df = pd.read_csv("latest.csv")

def make_lower_case(words_list):
    lower_cased_words = []
    for word in words_list:
        lower_cased_words.append(word.lower())
    return lower_cased_words

def listToString(s):
    str1 = ""
    for item in s:
        item = item + " "
        str1 += item
    return str1

#Remove  stop words, like: 'a, in' etc
def remove_stopwords(list_of_checked_words):
    tokens_without_sw = [
        word for word in list_of_checked_words if not word in stopwords.words()]
    return tokens_without_sw

#Compare the sentiment between the video-ad data and the given article/text
def sentiment_analysis(text, modelname="nlptown/bert-base-multilingual-uncased-sentiment"):
    text_labels = {'1 star': 'very negative', '2 stars': 'negative', '3 stars': 'neutral',
                   '4 stars': 'positive', '5 stars': 'very positive'}
    sentiment_analyse = pipeline(model=modelname)
    sentiment_article = sentiment_analyse(text[0])[0]
    sentiment_ad = sentiment_analyse(text[1])[0]

    return f"Article sentiment: <strong>{text_labels.get(sentiment_article['label'])}</strong>,  " \
           f"with confidence score of: <strong>{sentiment_article['score']*100:.3f}%</strong>" \
           f"<br/>Advert sentiment: <strong>{text_labels.get(sentiment_ad['label'])}</strong>, " \
           f"with confidence score of: <strong>{sentiment_ad['score']*100:.3f}%</strong>"

#Extract the most important keywords from the video-ad and the given article/text
def keywords_extracting(text, mmr, diversity, n_results, stop_words='english', modelname="paraphrase-multilingual-MiniLM-L12-v2"):
    # paraphrase-multilingual-mpnet-base-v2 or paraphrase-mpnet-base-v2

    #Manually removing stopwords because BERT doesn't comprehend Dutch
    filtered_article = ' '.join([word for word in text[0].split() if word not in set(stopwords.words(stop_words))])
    filtered_ad = ' '.join([word for word in text[1].split() if word not in set(stopwords.words(stop_words))])

    kw_model = KeyBERT(modelname)
    keywords_article = kw_model.extract_keywords(filtered_article, use_mmr=mmr, diversity=diversity, top_n=n_results)
    keywords_ad = kw_model.extract_keywords(filtered_ad, use_mmr=mmr, diversity=diversity, top_n=n_results)

    return keywords_article, keywords_ad

#See the similarity based on text between the video-ad and the given article/text
def semantic_textual_similarity(text, modelname="sentence-transformers/distiluse-base-multilingual-cased"):
    model = SentenceTransformer(modelname)
    embeddings = model.encode(text)
    sim = util.cos_sim(embeddings[0], embeddings[1])
    return f"The article and the ad are <strong>{sim.tolist()[0][0]*100:.3f}%</storng> similar."

#The app it self, the website is been generated by this part of the code. Turbo-Flask (library) makes it responsive to the user input
#without needing to reload the page.
@app.route("/", methods=["GET", "POST"])
def main():
    if request.method == "POST":

        web_data = []
        cleaned_article_text = []

        text = str(request.form.get("input"))

        web_data = remove_stopwords(make_lower_case(
                 tokenizer.tokenize(text)))
            
        cleaned_article_text.append(listToString(web_data))

        bert_model = joblib.load("bert_model.pkl")
        descp1_embedding = bert_model.encode(cleaned_article_text)

        all_similarity = []
        all_links = []
        all_vid_info = []
        prediction_list = []

        for vid, vid_link in zip(df.logo_label_text, df.youtube_url):
            sentence = []
            sentence.append(vid)
            descp2_embedding = bert_model.encode(sentence)
            all_similarity.append(cosine_similarity(
                [descp1_embedding[0]], [descp2_embedding[0]]))
            all_vid_info.append(vid)
            all_links.append(vid_link)
            prediction_list = [all_links, all_vid_info, all_similarity]
            # get max value of the similarity score

        #Check how similar the ads and the text are, provide the best result as a prediction
        prediction = cosine_similarity(
            [descp1_embedding[0]], [descp2_embedding[0]])

        # get the highest similarity
        max_similarity_index = prediction_list[2].index(
            max(prediction_list[2]))

        # Get the youtube link with the highest simlarity index
        prediction = prediction_list[0][max_similarity_index]
        vid_logo_label = prediction_list[1][max_similarity_index]
        
        #default values when the options are not selected
        output_analysis = 'Currently Unavailable. A sentiment score will be placed here once you have selected the option.'
        output_keywords = 'Currently Unavailable. A keyword analysis will be shown here once you have selected the option.'
        output_similarity = 'Currently Unavailable. A similarity score will be placed here once you have selected the option.'
        
        #The toggles for the various options/checkboxes and calling their functions
        text_vid = [text, vid_logo_label]
        if request.form.getlist("sntmnt_checkbox"):
            s_analysis = sentiment_analysis(text_vid)
            output_analysis = s_analysis
        if request.form.getlist("kwrd_checkbox"):
            #mmr and diversity are numbers to tweak the returned result. n_results is for how many results you want.
            keyword_analysis = keywords_extracting(text_vid, mmr=0.50, diversity=0.50, n_results=10)
            output_keywords = keyword_analysis
        if request.form.getlist("smlrty_checkbox"):
            similarity_analysis = semantic_textual_similarity(text_vid)
            output_similarity = similarity_analysis

        output_labels = str(vid_logo_label)
        output_review = '<button type="button" class="btn btn-primary" data-toggle="modal" data-target="#analysisModal">Review analysis</button>'

        p = prediction.replace("watch?v=", "embed/")
        output_ad = '<iframe width="420" height="315", src =' + p + '></iframe>'

        if 'Article sentiment: <strong>negative</strong>' in output_analysis:
            output_ad = '<p>Please note that the article sentiment is negative. Do you still want this ad to appear?</p></br><iframe width="420" height="315", src =' + p + '></iframe>'

        if 'Article sentiment: <strong>very negative</strong>' in output_analysis:
            output_ad = '<p><strong>Brand safety response:</strong> No ad has been placed due to the article having a <strong>very negative</strong> sentiment. Please review the analysis for more information.</p>'
        
        #The outputs placed in turboframes, updated on the webpage
        return turbo.stream([
            turbo.update(output_ad, target='advert'),
            turbo.update(output_review, target='modalButton'),
            turbo.update(output_analysis, target='sentiment'),
            turbo.update(output_keywords, target='keywords'),
            turbo.update(output_similarity, target='similarity'),
            turbo.update(cleaned_article_text, target='cleaned_article_text'),
            turbo.update(output_labels, target='videoLabels') #TO-DO: create a table for clearer view of the labels
        ])
    else:
        prediction = ""
    #render the webpage
    return render_template('test.html', output=prediction.replace("watch?v=", "embed/"))

    # Running the app
if __name__ == "__main__":
    app.run(debug=True, host=('0.0.0.0'))
