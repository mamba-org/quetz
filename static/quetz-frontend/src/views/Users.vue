<template>
<div class="bx--grid">
  <div class="bx--row">
    <div class="bx--col-lg-13 bx--offset-lg-3">
        <h1>Users</h1>
        <cv-data-table
          :columns="columns" :data="data" ref="table"></cv-data-table>

    </div>
  </div>
</div>
</template>


<script>
  export default {
    data: function () {
      return {
        columns: [],
        data: [],
        loading: true
      }
    },
    methods: {
      fetchData: function() {
        return fetch("/api/users").then((msg) => {
          console.log(msg);
          return msg.json().then((decoded) => {
              this.columns = ["Username", "Name", "Avatar URL"];
              this.data = decoded.map((el) => [el.username, el.profile.name, el.profile.avatar_url]);
          });
        });
      }
    },
    created: function() {
      this.fetchData();
    },
}
</script>

<style>
html {
   height: 100%;
}

body, #app {
   min-height: 100%;
}

</style>
