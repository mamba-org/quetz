<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3 quetz-main-table">
      <h3 class="bx--data-table-header">Generate an API Key</h3>
        <cv-text-input
          label="API Key Description"
          helper-text="Give your API Key a descriptive description"
          placeholder="My First API Key"
          id="apikey_description"
          v-model="description">
        </cv-text-input>
        <cv-button kind="secondary" @click="requestApiKey">
          Request API Key
        </cv-button>
      <cv-modal
        ref="modal">
          <template slot="title">API Key Retrieved!</template>
          <template slot="content"><em>Copy this key. This is the only time you can see it!</em>
          <p style="text-align: center; font-weight: bold; margin: 10px 0px; font-size: 1.5em">{{api_key}}</p></template>
          <template slot="primary-button">Close</template>
      </cv-modal>
    </div>
  </div>
</div>
</template>

<script>
  export default {
    data: () => {
      let today = new Date();
      return {
        description: "My Api Key " + today.toDateString(),
        response: {}
      };
    },
    computed: {
      api_key: function() {
        if (this.response) {
          return this.response.key;
        } else {
          return "No API Key retrieved.";
        }
      }
    },
    props: {
    },
    methods: {
      requestApiKey: function() {
        const requestOptions = {
          method: "POST",
          // headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description: "", roles: []  })
        };
        fetch("/api/api-keys", requestOptions)
          .then((response) => {
            response.json().then((parsed) => {
              // console.log(parsed)
              this.response = parsed;
              // this.api_key = parsed.key;
              this.$refs.modal.show()
            });
          })
      },
    }
  }
</script>