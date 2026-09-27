/**
 * SupportNova Gmail relay.
 *
 * Render's free plan blocks outbound SMTP, so the backend cannot log in to
 * smtp.gmail.com. This tiny web app runs inside the Gmail account itself and
 * sends the reply there, over ordinary HTTPS.
 *
 * Setup (signed in as the support Gmail account):
 *   1. https://script.google.com -> New project -> paste this file.
 *   2. Put the same long random string here and in Render's EMAIL_RELAY_SECRET.
 *   3. Deploy -> New deployment -> type "Web app"; Execute as: Me;
 *      Who has access: Anyone. Authorise when asked.
 *   4. Copy the Web app URL (ends in /exec) into Render's EMAIL_RELAY_URL.
 * Free Gmail accounts may send about 100 emails a day this way.
 */
var SECRET = 'PASTE-THE-SAME-SECRET-AS-EMAIL_RELAY_SECRET';

function doPost(e) {
  try {
    var d = JSON.parse(e.postData.contents);
    if (!SECRET || SECRET.indexOf('PASTE-') === 0 || d.secret !== SECRET) return reply({ ok: false, error: 'bad secret' });
    var options = { htmlBody: d.html, name: d.fromName || 'RaftarXpress Customer Care' };
    if (d.logo) {
      var images = {};
      images[d.logoCid || 'supportnova-logo'] = Utilities.newBlob(Utilities.base64Decode(d.logo), 'image/png', 'supportnova.png');
      options.inlineImages = images;
    }
    MailApp.sendEmail(d.to, d.subject, d.text || '', options);
    return reply({ ok: true, remaining: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

function reply(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
