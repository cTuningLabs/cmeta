/*

JavaScript Functions to access cMeta server.

Copyright (c) 2025 Grigori Fursin and cTuning Labs. 

Apache License, Version 2.0.

*/

async function accessCT(api_url, dict, uploadInput) {

  const formData = dict;

  if (uploadInput && uploadInput.files && uploadInput.files.length == 1) {
    formData.append("file", uploadInput.files[0]);
  }

  var csrftoken = getCTCookie('csrftoken');
  var output = {'return':9, 'error':'empty output'};

  console.log(api_url);

  const r = await fetch(api_url,
    {
      method: "POST",
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
      },
      body: JSON.stringify(formData),
      mode: 'cors',
      cache: 'default'
    }).then(response => {
      if (!response.ok)
        return {'return':127, 'error':'cMeta server API returned error: '+response.statusText};
      return response.json();
    }).then(function (data) {
      output = data;
    }).catch(function(error) {
      output = {'return':127, 'error':'Error while accessing the cMeta server API: '+error}
    });

  return output;
}

// Get specific cookie
function getCTCookie(name) {
  var cookieValue = null;
  if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
          var cookie = cookies[i].trim();
          if (cookie.substring(0, name.length + 1) === (name + '=')) {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
          }
      }
  }
  return cookieValue;
};
